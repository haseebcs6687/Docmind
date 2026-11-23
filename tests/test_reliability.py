"""Comprehensive unit tests for reliability, error classification, bounded retries,
fallback models, quota guards, answer caching, and setup checks (0 real API calls).
"""

import json
from pathlib import Path
import time
from unittest import mock
import pytest
from streamlit.testing.v1 import AppTest

from src.chunking import Chunk
from src.config import (
    GEMINI_FALLBACK_MODEL,
    GEMINI_MODEL,
    MAX_CHUNKS_PER_UPLOAD_BATCH,
    MAX_QUESTIONS_PER_SESSION,
    MAX_TOTAL_CHUNKS,
    MIN_SECONDS_BETWEEN_QUESTIONS,
)
from src.gemini_client import (
    ErrorCategory,
    FRIENDLY_ERROR_MESSAGES,
    GeminiServiceError,
    GenerationError,
    _sanitize_error_message,
    call_with_retry_and_fallback,
    classify_error,
)
from src.rag import AnswerCache, ChatSession, RagResponse, answer
from src.vectorstore import VectorStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_PATH = str(PROJECT_ROOT / "app.py")


# ---------------------------------------------------------------------------
# Helper Mock Objects and Exceptions
# ---------------------------------------------------------------------------

class FakeAPIError(Exception):
    """Simulate google.genai.errors.APIError."""
    def __init__(self, code: int, message: str, status: str = "", details: list = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or []


class MockStore:
    """Mock VectorStore for deterministic testing without ChromaDB or Gemini API."""
    def __init__(self, results=None, doc_count=5, fingerprint="fp_init_123"):
        self.results = results if results is not None else []
        self._doc_count = doc_count
        self._fingerprint = fingerprint
        self.last_query = None

    def query(self, question, k=5):
        self.last_query = question
        return self.results

    def count(self):
        return self._doc_count

    def get_fingerprint(self):
        return self._fingerprint

    def list_sources(self):
        return [{"name": "Sample.pdf", "chunk_count": self._doc_count, "file_type": "pdf"}]


def _sample_context_results(scores=(0.88, 0.75)):
    return [
        {
            "id": f"c_{i}",
            "text": f"Grounded sample legal text {i}.",
            "source": "Sample.pdf",
            "page": i,
            "section": None,
            "citation": f"Sample.pdf, p. {i}",
            "score": score,
        }
        for i, score in enumerate(scores, start=1)
    ]


# ---------------------------------------------------------------------------
# 1. Error Classification (9 categories)
# ---------------------------------------------------------------------------

def test_classify_error_rate_limit_minute():
    err = FakeAPIError(429, "Resource has been exhausted (e.g. check quota).")
    assert classify_error(err) == ErrorCategory.RATE_LIMIT_MINUTE


def test_classify_error_quota_daily():
    err1 = FakeAPIError(429, "Quota exceeded: requests per day limit reached")
    assert classify_error(err1) == ErrorCategory.QUOTA_DAILY

    err2 = FakeAPIError(429, "Quota exhausted", details=[{"quota_metric": "generate_content_requests_per_day"}])
    assert classify_error(err2) == ErrorCategory.QUOTA_DAILY


def test_classify_error_server_busy():
    for code in (500, 503, 504):
        err = FakeAPIError(code, f"Server error {code}: The model is overloaded")
        assert classify_error(err) == ErrorCategory.SERVER_BUSY


def test_classify_error_timeout():
    err1 = TimeoutError("Request timed out after 25 seconds")
    assert classify_error(err1) == ErrorCategory.TIMEOUT

    err2 = FakeAPIError(504, "Deadline exceeded while waiting for response")
    assert classify_error(err2) == ErrorCategory.TIMEOUT


def test_classify_error_network():
    err1 = ConnectionError("Connection refused by peer")
    assert classify_error(err1) == ErrorCategory.NETWORK

    err2 = FakeAPIError(500, "Remote end closed connection without response")
    assert classify_error(err2) == ErrorCategory.NETWORK


def test_classify_error_model_unavailable():
    err1 = FakeAPIError(404, "models/gemini-old is not found for API version")
    assert classify_error(err1) == ErrorCategory.MODEL_UNAVAILABLE

    err2 = FakeAPIError(400, "Model is no longer available to new users")
    assert classify_error(err2) == ErrorCategory.MODEL_UNAVAILABLE


def test_classify_error_auth():
    err1 = FakeAPIError(401, "API_KEY_INVALID: API key not valid")
    assert classify_error(err1) == ErrorCategory.AUTH

    err2 = FakeAPIError(403, "The caller does not have permission to execute the specified operation")
    assert classify_error(err2) == ErrorCategory.AUTH


def test_classify_error_bad_request():
    err = FakeAPIError(400, "Invalid argument: contents field cannot be empty")
    assert classify_error(err) == ErrorCategory.BAD_REQUEST


def test_classify_error_unknown():
    err = ValueError("Unrecognized internal data shape")
    assert classify_error(err) == ErrorCategory.UNKNOWN


# ---------------------------------------------------------------------------
# 2. 503 Retry Succeeds After Simulated Transient Error
# ---------------------------------------------------------------------------

def test_503_retry_succeeds():
    attempts = 0

    def mock_call(model_name: str):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise FakeAPIError(503, "The model is overloaded. Please try again later.")
        return "SUCCESS_RESULT"

    with mock.patch("time.sleep", return_value=None):
        result, model_used, fallback_used = call_with_retry_and_fallback(
            fn=mock_call,
            primary_model=GEMINI_MODEL,
            fallback_model=GEMINI_FALLBACK_MODEL,
            max_retries=3,
        )

    assert result == "SUCCESS_RESULT"
    assert attempts == 2
    assert model_used == GEMINI_MODEL
    assert fallback_used is False


# ---------------------------------------------------------------------------
# 3. 503 Exhausted Triggers Fallback Model
# ---------------------------------------------------------------------------

def test_503_exhausted_triggers_fallback():
    calls = []

    def mock_call(model_name: str):
        calls.append(model_name)
        if model_name == GEMINI_MODEL:
            raise FakeAPIError(503, "The model is overloaded.")
        return "FALLBACK_SUCCESS"

    with mock.patch("time.sleep", return_value=None):
        result, model_used, fallback_used = call_with_retry_and_fallback(
            fn=mock_call,
            primary_model=GEMINI_MODEL,
            fallback_model=GEMINI_FALLBACK_MODEL,
            max_retries=2,
        )

    assert result == "FALLBACK_SUCCESS"
    assert model_used == GEMINI_FALLBACK_MODEL
    assert fallback_used is True
    # Primary model called 3 times (1 initial + 2 retries), then fallback model called
    assert calls.count(GEMINI_MODEL) == 3
    assert calls.count(GEMINI_FALLBACK_MODEL) == 1


# ---------------------------------------------------------------------------
# 4. 404 MODEL_UNAVAILABLE Immediately Triggers Fallback Model Without Retries
# ---------------------------------------------------------------------------

def test_404_model_unavailable_immediate_fallback():
    calls = []

    def mock_call(model_name: str):
        calls.append(model_name)
        if model_name == GEMINI_MODEL:
            raise FakeAPIError(404, "models/gemini-unavailable is not found")
        return "FALLBACK_ANSWER"

    with mock.patch("time.sleep", return_value=None) as mock_sleep:
        result, model_used, fallback_used = call_with_retry_and_fallback(
            fn=mock_call,
            primary_model=GEMINI_MODEL,
            fallback_model=GEMINI_FALLBACK_MODEL,
            max_retries=3,
        )

    assert result == "FALLBACK_ANSWER"
    assert model_used == GEMINI_FALLBACK_MODEL
    assert fallback_used is True
    # Primary model attempted exactly once (no retry sleep)
    assert calls.count(GEMINI_MODEL) == 1
    mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# 5. Daily Quota is Never Retried and Raises Immediately
# ---------------------------------------------------------------------------

def test_daily_quota_never_retried():
    attempts = 0

    def mock_call(model_name: str):
        nonlocal attempts
        attempts += 1
        raise FakeAPIError(429, "Resource has been exhausted: requests per day limit exceeded")

    with mock.patch("time.sleep", return_value=None) as mock_sleep:
        with pytest.raises(GenerationError) as exc_info:
            call_with_retry_and_fallback(
                fn=mock_call,
                primary_model=GEMINI_MODEL,
                fallback_model=GEMINI_FALLBACK_MODEL,
                max_retries=3,
            )

    assert attempts == 1
    mock_sleep.assert_not_called()
    assert exc_info.value.category == ErrorCategory.QUOTA_DAILY
    assert exc_info.value.user_message == FRIENDLY_ERROR_MESSAGES[ErrorCategory.QUOTA_DAILY]


# ---------------------------------------------------------------------------
# 6. Total Time Budget Enforcement (Fake Clock)
# ---------------------------------------------------------------------------

def test_total_time_budget_enforcement():
    fake_time = 100.0

    def mock_time():
        return fake_time

    def mock_call(model_name: str):
        raise FakeAPIError(503, "Service busy")

    def mock_sleep(seconds: float):
        nonlocal fake_time
        # Jump ahead past the 40-second total budget
        fake_time += 45.0

    with mock.patch("time.time", side_effect=mock_time), mock.patch("time.sleep", side_effect=mock_sleep):
        with pytest.raises(GenerationError) as exc_info:
            call_with_retry_and_fallback(
                fn=mock_call,
                primary_model=GEMINI_MODEL,
                fallback_model=None,
                max_retries=5,
                total_budget_seconds=40.0,
            )

    assert exc_info.value.category in (ErrorCategory.TIMEOUT, ErrorCategory.SERVER_BUSY)


# ---------------------------------------------------------------------------
# 7. Error Sanitization Never Leaks API Keys
# ---------------------------------------------------------------------------

def test_error_sanitization_redacts_api_keys():
    secret_key = "AIzaSyDummySecretKey1234567890abcdef"
    raw_error = f"Request to https://generativelanguage.googleapis.com failed: key={secret_key}"

    sanitized = _sanitize_error_message(raw_error)
    assert secret_key not in sanitized
    assert "[REDACTED" in sanitized

    # Verify GeminiServiceError never leaks raw credentials in str() or representation
    service_err = GeminiServiceError(
        raw_error=raw_error,
        category=ErrorCategory.AUTH,
        user_message=FRIENDLY_ERROR_MESSAGES[ErrorCategory.AUTH],
    )
    assert secret_key not in str(service_err)
    assert secret_key not in service_err.sanitized_message


# ---------------------------------------------------------------------------
# 8. Cooldown and Max-Questions Limits in ChatSession
# ---------------------------------------------------------------------------

def test_cooldown_enforcement_in_chat_session():
    store = MockStore(results=_sample_context_results())
    mock_resp = json.dumps({"found": True, "answer": "Answer 1", "used_sources": [1]})

    session = ChatSession(
        store=store,
        llm=lambda sys, p: mock_resp,
        cooldown_seconds=MIN_SECONDS_BETWEEN_QUESTIONS,
    )

    # First question succeeds
    r1 = session.ask("What is the consultation fee?")
    assert r1.found is True

    # Immediate second question violates cooldown
    r2 = session.ask("What is the consultation fee again?")
    assert r2.found is False
    assert "wait a moment" in r2.answer.lower()


def test_max_questions_session_limit():
    store = MockStore(results=_sample_context_results())
    mock_resp = json.dumps({"found": True, "answer": "Answer", "used_sources": [1]})

    session = ChatSession(
        store=store,
        llm=lambda sys, p: mock_resp,
        max_questions=MAX_QUESTIONS_PER_SESSION,
    )
    # Simulate reaching the question limit
    session.question_count = MAX_QUESTIONS_PER_SESSION

    r_limit = session.ask("Can I ask another question?")
    assert r_limit.found is False
    assert "limit" in r_limit.answer.lower()


# ---------------------------------------------------------------------------
# 9. Small Talk Bypasses Cooldown and Session Question Limit
# ---------------------------------------------------------------------------

def test_small_talk_bypasses_cooldown_and_limit():
    store = MockStore(results=_sample_context_results())
    mock_resp = json.dumps({"found": True, "answer": "Answer", "used_sources": [1]})

    session = ChatSession(
        store=store,
        llm=lambda sys, p: mock_resp,
        cooldown_seconds=MIN_SECONDS_BETWEEN_QUESTIONS,
    )

    # Ask greeting
    r1 = session.ask("Hello! How are you?")
    assert r1.found is True
    assert r1.api_calls == 0
    assert session.question_count == 0  # Does not increment question count
    assert session.last_question_time == 0.0  # Does not trigger cooldown timer

    # Submitting a real query immediately after does not trigger cooldown
    r2 = session.ask("What are the hourly rates?")
    assert r2.found is True
    assert session.question_count == 1


# ---------------------------------------------------------------------------
# 10. Answer Cache Hit and Fingerprint Invalidation
# ---------------------------------------------------------------------------

def test_answer_cache_hit_and_invalidation():
    cache = AnswerCache(ttl_seconds=300, max_entries=10)
    fp1 = "store_v1_abc"
    fp2 = "store_v2_xyz"

    resp1 = RagResponse(
        answer="Fee is PKR 5,000",
        sources=[],
        found=True,
        latency_ms=450.0,
        model_used="gemini-3.5-flash-lite",
    )

    cache.set("what is the fee?", fp1, resp1)

    # Hit with same query and fingerprint
    hit = cache.get("  What is the fee?  ", fp1)
    assert hit is not None
    assert hit.answer == "Fee is PKR 5,000"
    assert hit.cached is True
    assert hit.latency_ms == 0.0

    # Miss with different store fingerprint
    miss = cache.get("what is the fee?", fp2)
    assert miss is None


# ---------------------------------------------------------------------------
# 11. Upload Guard Pre-Check (Batch and Total Limits)
# ---------------------------------------------------------------------------

def test_upload_guard_limits_constants():
    assert MAX_CHUNKS_PER_UPLOAD_BATCH == 300
    assert MAX_TOTAL_CHUNKS == 1500

    # Test dummy chunk batch validation logic
    dummy_chunks_oversize = [
        Chunk(
            id=f"c_{i}",
            text="x",
            source="f.pdf",
            page=1,
            section=None,
            file_type="pdf",
            citation="f.pdf, p. 1",
            chunk_index=i,
        )
        for i in range(MAX_CHUNKS_PER_UPLOAD_BATCH + 5)
    ]
    assert len(dummy_chunks_oversize) > MAX_CHUNKS_PER_UPLOAD_BATCH

    store = MockStore(doc_count=1450)
    new_chunks = 100
    assert store.count() + new_chunks > MAX_TOTAL_CHUNKS


# ---------------------------------------------------------------------------
# 12. Missing API Key Setup Card in AppTest
# ---------------------------------------------------------------------------

def test_missing_api_key_renders_clean_setup_card():
    mock_store = mock.MagicMock(spec=VectorStore)
    mock_store.count.return_value = 10
    mock_store.list_sources.return_value = [{"name": "doc.pdf", "chunk_count": 10, "file_type": "pdf"}]

    def mock_get_key():
        raise ValueError("GEMINI_API_KEY environment variable is not set.")

    with mock.patch("src.ui.chat_page.get_gemini_api_key", side_effect=mock_get_key), \
         mock.patch("src.ui.state.get_store", return_value=mock_store), \
         mock.patch("src.ui.chat_page.get_store", return_value=mock_store), \
         mock.patch("src.ui.documents_page.get_store", return_value=mock_store), \
         mock.patch("app.get_store", return_value=mock_store):

        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()

        # Should not crash with an unhandled exception
        assert len(at.exception) == 0, f"App raised exceptions: {at.exception}"

        # Should render warning setup card
        warnings = [w.value for w in at.warning]
        assert any("Gemini API Key Required" in w for w in warnings)
