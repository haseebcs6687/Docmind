"""Centralized Gemini client factory, error classification, bounded retries, and fallback handling."""

from enum import Enum
import logging
import random
import re
import time
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

from src.config import (
    DEMO_MODE,
    GEMINI_FALLBACK_MODEL,
    GEMINI_MODEL,
    GEMINI_TIMEOUT_SECONDS,
    GEN_ANALYSIS_TIMEOUT_SECONDS,
    GEN_FALLBACK_ATTEMPTS,
    GEN_MAX_RETRIES,
    GEN_PRIMARY_ATTEMPTS,
    GEN_TOTAL_BUDGET_SECONDS,
    get_gemini_api_key,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Process-level set tracking models that reject thinking_config (400 INVALID_ARGUMENT)
_MODELS_REJECTING_THINKING: set[str] = set()


def record_model_rejects_thinking(model_name: str) -> None:
    """Record that a model does not support thinking_config."""
    if model_name:
        _MODELS_REJECTING_THINKING.add(model_name)


def model_rejects_thinking(model_name: str) -> bool:
    """Return True if the model is known to reject thinking_config."""
    return model_name in _MODELS_REJECTING_THINKING


class ErrorCategory(str, Enum):
    """Categorized API and service error types."""

    RATE_LIMIT_MINUTE = "RATE_LIMIT_MINUTE"
    QUOTA_DAILY = "QUOTA_DAILY"
    SERVER_BUSY = "SERVER_BUSY"
    TIMEOUT = "TIMEOUT"
    NETWORK = "NETWORK"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    AUTH = "AUTH"
    BAD_REQUEST = "BAD_REQUEST"
    UNKNOWN = "UNKNOWN"


FRIENDLY_ERROR_MESSAGES: Dict[ErrorCategory, str] = {
    ErrorCategory.SERVER_BUSY: "The AI service is busy right now. Please try again in a few seconds.",
    ErrorCategory.RATE_LIMIT_MINUTE: "Too many requests. Please wait a moment and try again.",
    ErrorCategory.QUOTA_DAILY: "The free daily quota for this demo has been reached. Please try again tomorrow.",
    ErrorCategory.TIMEOUT: "The request took too long. Please try again.",
    ErrorCategory.NETWORK: "Can't reach the AI service. Check the connection and try again.",
    ErrorCategory.AUTH: "The service is not configured correctly. Please contact the site owner.",
    ErrorCategory.BAD_REQUEST: "Something went wrong. Please try again.",
    ErrorCategory.MODEL_UNAVAILABLE: "The AI model is currently unavailable. Please try again later.",
    ErrorCategory.UNKNOWN: "Something went wrong. Please try again.",
}


def _sanitize_error_message(err: Any) -> str:
    """Strip accidental credentials, keys, or internal API tokens from error strings."""
    msg = str(err)
    msg = re.sub(r"AIza[0-9A-Za-z-_]{20,}", "[REDACTED_KEY]", msg)
    msg = re.sub(
        r"(?:api[_-]?key|key)[\s=:'\"]+([0-9A-Za-z-_]+)",
        r"key=[REDACTED]",
        msg,
        flags=re.IGNORECASE,
    )
    return msg[:200]


class GeminiServiceError(Exception):
    """Base exception for categorized Gemini API service errors with sanitized user messages."""

    def __init__(
        self,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        message: str = "",
        original_error: Optional[Exception] = None,
        user_message: Optional[str] = None,
        raw_error: Optional[Any] = None,
    ):
        self.category = category
        self.user_message = user_message or FRIENDLY_ERROR_MESSAGES.get(
            category, FRIENDLY_ERROR_MESSAGES[ErrorCategory.UNKNOWN]
        )
        msg_to_sanitize = message or (str(raw_error) if raw_error is not None else self.user_message)
        self.sanitized_message = _sanitize_error_message(msg_to_sanitize)
        self.original_error = original_error or (raw_error if isinstance(raw_error, Exception) else None)
        # Display sanitized message in str() if a specific error message was given; otherwise friendly user message
        display_msg = self.sanitized_message if (message or raw_error) else self.user_message
        super().__init__(display_msg)


class GenerationError(GeminiServiceError):
    """Raised when text generation fails after retries or due to non-retryable errors."""

    pass


class EmbeddingError(GeminiServiceError):
    """Raised when embedding generation fails after retries or due to non-retryable errors."""

    pass


def classify_error(err: Exception) -> ErrorCategory:
    """Classify an arbitrary exception into a standard ErrorCategory enum."""
    if isinstance(err, GeminiServiceError):
        return err.category

    err_str = str(err).lower()
    code = getattr(err, "code", None) or getattr(err, "status_code", None)
    status = str(getattr(err, "status", "")).upper()
    details_str = str(getattr(err, "details", "")).lower()
    combined = f"{err_str} {details_str} {status.lower()}"

    # 1. Quota / Rate limit (HTTP 429 or RESOURCE_EXHAUSTED)
    if code == 429 or status == "RESOURCE_EXHAUSTED" or "429" in err_str or "resource_exhausted" in combined:
        daily_indicators = ["per_day", "per day", "daily", "requestsperday", "rpd"]
        if any(ind in combined for ind in daily_indicators):
            return ErrorCategory.QUOTA_DAILY
        return ErrorCategory.RATE_LIMIT_MINUTE

    # 2. Auth (401, 403, PERMISSION_DENIED, UNAUTHENTICATED, API_KEY_INVALID)
    if (
        code in (401, 403)
        or status in ("PERMISSION_DENIED", "UNAUTHENTICATED")
        or any(s in combined for s in ("api_key", "unauthenticated", "permission_denied", "invalid api key"))
    ):
        return ErrorCategory.AUTH

    # 3. Model Unavailable (404, NOT_FOUND, no longer available)
    if code == 404 or status == "NOT_FOUND" or "not found" in combined or "no longer available" in combined:
        return ErrorCategory.MODEL_UNAVAILABLE

    # 4. Timeout (TimeoutError, deadline exceeded, timeout string, or HTTP 408)
    if (
        isinstance(err, TimeoutError)
        or "timeout" in combined
        or "timed out" in combined
        or "deadline exceeded" in combined
        or code == 408
    ):
        return ErrorCategory.TIMEOUT

    # 5. Network (ConnectionError, broken pipe, connection reset, connection refused, remote disconnected)
    if (
        isinstance(err, (ConnectionError, OSError))
        or any(
            s in combined
            for s in (
                "connecterror",
                "networkerror",
                "connection error",
                "connection reset",
                "transport error",
                "connection refused",
                "remote end closed",
                "remotedisconnected",
                "getaddrinfo",
            )
        )
    ):
        return ErrorCategory.NETWORK

    # 6. Bad Request (400, INVALID_ARGUMENT)
    if code == 400 or status == "INVALID_ARGUMENT" or "bad request" in combined:
        return ErrorCategory.BAD_REQUEST

    # 7. Server Busy (500, 502, 503, 504, UNAVAILABLE, INTERNAL)
    if (
        code in (500, 502, 503, 504)
        or status in ("UNAVAILABLE", "INTERNAL")
        or any(s in err_str for s in ("503", "502", "504", "server error", "service unavailable", "overloaded"))
    ):
        return ErrorCategory.SERVER_BUSY

    return ErrorCategory.UNKNOWN


def create_gemini_client(
    api_key: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Any:
    """Create a configured Gemini Client instance with explicit timeout and SDK retries disabled.

    Internal retries are disabled by passing HttpRetryOptions(attempts=1) to ensure
    our custom retry loop is the single, observable retry layer with bounded latency.
    """
    from google import genai
    from google.genai import types

    key = api_key or get_gemini_api_key()
    req_timeout_sec = timeout or GEMINI_TIMEOUT_SECONDS
    # Note: google-genai HttpOptions.timeout is in milliseconds
    timeout_ms = int(req_timeout_sec * 1000)

    http_opts = types.HttpOptions(
        timeout=timeout_ms,
        retry_options=types.HttpRetryOptions(attempts=1),
    )
    return genai.Client(api_key=key, http_options=http_opts)


def call_with_retry_and_fallback(
    call_fn: Optional[Callable[[str], T]] = None,
    primary_model: str = GEMINI_MODEL,
    fallback_model: Optional[str] = None,
    primary_attempts: int = GEN_PRIMARY_ATTEMPTS,
    fallback_attempts: int = GEN_FALLBACK_ATTEMPTS,
    total_budget_seconds: float = GEN_TOTAL_BUDGET_SECONDS,
    clock: Optional[Callable[[], float]] = None,
    sleeper: Optional[Callable[[float], None]] = None,
    fn: Optional[Callable[[str], T]] = None,
    max_retries: Optional[int] = None,
) -> Tuple[T, str, bool]:
    """Execute an API call with early failover, bounded retries, and total time budget.

    Architecture (Early Failover):
    - Primary attempts: bounded by primary_attempts (default GEN_PRIMARY_ATTEMPTS = 2).
    - Primary budget: bounded by total_budget_seconds / 2.0 (so fallback always gets time).
    - After primary's attempts fail with SERVER_BUSY, TIMEOUT, NETWORK (or MODEL_UNAVAILABLE),
      switches immediately to fallback_model.
    - Fallback attempts: bounded by fallback_attempts (default GEN_FALLBACK_ATTEMPTS = 2).
    - Non-retryable errors (QUOTA_DAILY, AUTH, BAD_REQUEST) are NEVER retried.
    """
    if clock is None:
        clock = time.time
    if sleeper is None:
        sleeper = time.sleep

    target_fn = call_fn if call_fn is not None else fn
    if target_fn is None:
        raise ValueError("A callable function must be provided to call_with_retry_and_fallback.")

    # Global daily generation budget check in demo mode (0 API calls when exhausted)
    if DEMO_MODE:
        from src.demo_limits import check_and_count_generation
        allowed, msg = check_and_count_generation()
        if not allowed:
            raise GenerationError(
                category=ErrorCategory.QUOTA_DAILY,
                message=msg or "Today's free demo capacity has been used up. Please come back tomorrow.",
            )

    # Backward compatibility: if max_retries is passed, respect it as an upper bound on primary attempts
    effective_primary_attempts = primary_attempts
    if max_retries is not None:
        effective_primary_attempts = min(primary_attempts, max_retries)

    start_time = clock()
    target_model = primary_model
    fallback_candidate = fallback_model if fallback_model is not None else GEMINI_FALLBACK_MODEL
    if not fallback_candidate or fallback_candidate == primary_model:
        fallback_candidate = None

    fallback_used = False
    attempts_made = 0
    backoff = 2.0
    primary_budget = total_budget_seconds / 2.0

    while True:
        elapsed = clock() - start_time
        if elapsed >= total_budget_seconds:
            raise GenerationError(
                ErrorCategory.TIMEOUT,
                f"Total retry budget of {total_budget_seconds}s exceeded."
            )

        # Before making attempt, check if primary budget is exhausted and switch to fallback
        if not fallback_used and fallback_candidate:
            if attempts_made >= effective_primary_attempts or elapsed >= primary_budget:
                logger.warning(
                    "Primary phase ended (attempts: %d/%d, elapsed: %.1fs/%.1fs); switching to fallback '%s'",
                    attempts_made, effective_primary_attempts, elapsed, primary_budget, fallback_candidate
                )
                target_model = fallback_candidate
                fallback_used = True
                attempts_made = 0
                backoff = 1.0

        try:
            result = target_fn(target_model)
            return result, target_model, fallback_used

        except Exception as e:
            cat = classify_error(e)

            # Non-retryable categories: NEVER retry
            if cat in (ErrorCategory.QUOTA_DAILY, ErrorCategory.AUTH, ErrorCategory.BAD_REQUEST):
                raise GenerationError(cat, str(e), original_error=e)

            # MODEL_UNAVAILABLE (404): Immediate failover to fallback if available
            if cat == ErrorCategory.MODEL_UNAVAILABLE:
                if fallback_candidate and not fallback_used:
                    logger.warning(
                        "Primary model '%s' unavailable (404); early failover to fallback model '%s'",
                        primary_model,
                        fallback_candidate,
                    )
                    target_model = fallback_candidate
                    fallback_used = True
                    attempts_made = 0
                    backoff = 1.0
                    continue
                raise GenerationError(cat, str(e), original_error=e)

            # Retryable categories: RATE_LIMIT_MINUTE, SERVER_BUSY, TIMEOUT, NETWORK
            is_retryable = cat in (
                ErrorCategory.RATE_LIMIT_MINUTE,
                ErrorCategory.SERVER_BUSY,
                ErrorCategory.TIMEOUT,
                ErrorCategory.NETWORK,
            )
            if not is_retryable:
                raise GenerationError(cat, str(e), original_error=e)

            attempts_made += 1
            now = clock()
            total_remaining = total_budget_seconds - (now - start_time)

            if not fallback_used and fallback_candidate:
                # Primary failed: check if attempts or primary budget exceeded
                primary_remaining = primary_budget - (now - start_time)
                if attempts_made >= effective_primary_attempts or primary_remaining <= 0:
                    logger.warning(
                        "Primary model '%s' failed attempt %d/%d with %s; early failover to fallback '%s'",
                        primary_model,
                        attempts_made,
                        effective_primary_attempts,
                        cat.value,
                        fallback_candidate,
                    )
                    target_model = fallback_candidate
                    fallback_used = True
                    attempts_made = 0
                    backoff = 1.0
                    continue

                # Retry primary
                wait_time = min(backoff + random.uniform(0.1, 0.4), primary_remaining, total_remaining)
                if wait_time <= 0:
                    # Time for primary up, failover immediately
                    target_model = fallback_candidate
                    fallback_used = True
                    attempts_made = 0
                    backoff = 1.0
                    continue

                logger.warning(
                    "[Retry primary] attempt %d/%d, wait %.2fs, error %s",
                    attempts_made,
                    effective_primary_attempts,
                    wait_time,
                    type(e).__name__,
                )
                sleeper(wait_time)
                backoff *= 2.0
            else:
                # We are in fallback phase (or primary without fallback)
                max_current = fallback_attempts if fallback_used else effective_primary_attempts
                if attempts_made >= max_current:
                    raise GenerationError(
                        cat,
                        f"Model '{target_model}' failed after {attempts_made} attempts: {e}",
                        original_error=e,
                    )

                wait_time = min(backoff + random.uniform(0.1, 0.4), total_remaining)
                if wait_time <= 0:
                    raise GenerationError(
                        ErrorCategory.TIMEOUT,
                        "Time budget exhausted while waiting for retry."
                    )

                logger.warning(
                    "[Retry %s] attempt %d/%d, wait %.2fs, error %s",
                    "fallback" if fallback_used else "primary",
                    attempts_made,
                    max_current,
                    wait_time,
                    type(e).__name__,
                )
                sleeper(wait_time)
                backoff *= 2.0
