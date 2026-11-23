"""Centralized Gemini client factory, error classification, bounded retries, and fallback handling."""

from enum import Enum
import logging
import random
import re
import time
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

from src.config import (
    GEMINI_FALLBACK_MODEL,
    GEMINI_MODEL,
    GEMINI_TIMEOUT_SECONDS,
    GEN_MAX_RETRIES,
    GEN_TOTAL_BUDGET_SECONDS,
    get_gemini_api_key,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


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
    max_retries: int = GEN_MAX_RETRIES,
    total_budget_seconds: float = GEN_TOTAL_BUDGET_SECONDS,
    clock: Callable[[], float] = time.time,
    sleeper: Callable[[float], None] = time.sleep,
    fn: Optional[Callable[[str], T]] = None,
) -> Tuple[T, str, bool]:
    """Execute an API call with bounded retries, total time budget, and fallback model.

    Args:
        call_fn: Callable taking model_name: str and returning result T (or fn alias).
        primary_model: Name of the primary model to invoke.
        fallback_model: Optional fallback model if primary fails with SERVER_BUSY, TIMEOUT, or MODEL_UNAVAILABLE.
        max_retries: Maximum retry attempts for transient errors on the active model.
        total_budget_seconds: Hard upper bound on elapsed time across all retries and fallback.
        clock: Monotonic or wall clock provider (injectable for unit tests).
        sleeper: Sleep function (injectable for unit tests).
        fn: Keyword alias for call_fn.

    Returns:
        Tuple of (result, model_used, fallback_used)

    Raises:
        GenerationError: When attempts are exhausted or a non-retryable error occurs.
    """
    target_fn = call_fn if call_fn is not None else fn
    if target_fn is None:
        raise ValueError("A callable function must be provided to call_with_retry_and_fallback.")

    start_time = clock()
    target_model = primary_model
    fallback_candidate = fallback_model or GEMINI_FALLBACK_MODEL
    fallback_used = False

    attempt = 0
    backoff = 1.0

    while True:
        elapsed = clock() - start_time
        if elapsed >= total_budget_seconds:
            raise GenerationError(
                ErrorCategory.TIMEOUT,
                f"Total retry budget of {total_budget_seconds}s exceeded."
            )

        try:
            result = target_fn(target_model)
            return result, target_model, fallback_used

        except Exception as e:
            cat = classify_error(e)

            # Non-retryable categories: never retry
            if cat in (ErrorCategory.QUOTA_DAILY, ErrorCategory.AUTH, ErrorCategory.BAD_REQUEST):
                raise GenerationError(cat, str(e), original_error=e)

            # MODEL_UNAVAILABLE: Immediate fallback candidate switch if available
            if cat == ErrorCategory.MODEL_UNAVAILABLE:
                if fallback_candidate and not fallback_used and target_model != fallback_candidate:
                    logger.warning(
                        "Primary model '%s' unavailable (404); attempting fallback model '%s'",
                        primary_model,
                        fallback_candidate,
                    )
                    target_model = fallback_candidate
                    fallback_used = True
                    attempt = 0
                    max_retries = 1
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

            if attempt < max_retries:
                attempt += 1
                remaining_budget = total_budget_seconds - (clock() - start_time)
                wait_time = min(backoff + random.uniform(0.1, 0.5), remaining_budget)
                if wait_time <= 0:
                    raise GenerationError(
                        ErrorCategory.TIMEOUT,
                        "Time budget exhausted while waiting for retry."
                    )

                logger.warning(
                    "[Retry] attempt %d/%d, wait %.2fs, error %s",
                    attempt,
                    max_retries,
                    wait_time,
                    type(e).__name__,
                )
                sleeper(wait_time)
                backoff *= 2.0
            else:
                # Primary model exhausted retries with SERVER_BUSY or TIMEOUT
                if (
                    fallback_candidate
                    and not fallback_used
                    and target_model != fallback_candidate
                    and cat in (ErrorCategory.SERVER_BUSY, ErrorCategory.TIMEOUT)
                ):
                    logger.warning(
                        "Primary model '%s' failed after %d retries with %s; switching to fallback model '%s'",
                        primary_model,
                        max_retries,
                        cat.value,
                        fallback_candidate,
                    )
                    target_model = fallback_candidate
                    fallback_used = True
                    attempt = 0
                    max_retries = 1
                    backoff = 1.0
                    continue

                raise GenerationError(cat, str(e), original_error=e)
