"""Unit tests for the DocMind RAG pipeline, guardrails, and language detection."""

import json
from unittest.mock import MagicMock
import pytest

from src.rag import (
    GenerationError,
    RagResponse,
    _call_gemini_with_retry,
    answer,
    detect_language,
    get_not_found_message,
    NOT_FOUND_EN,
    NOT_FOUND_ROMAN,
    NOT_FOUND_URDU,
)


class MockStore:
    """Mock VectorStore for deterministic unit testing without ChromaDB or Gemini API."""

    def __init__(self, results=None, doc_count=5):
        self.results = results if results is not None else []
        self._doc_count = doc_count

    def query(self, question, k=5):
        return self.results

    def count(self):
        return self._doc_count


def _sample_context_results(scores=(0.85, 0.75, 0.70)):
    """Generate sample query results matching VectorStore return format."""
    results = []
    for i, s in enumerate(scores, start=1):
        results.append({
            "id": f"chunk_{i}",
            "text": f"This is sample passage {i} discussing legal fees and consultation terms.",
            "source": f"doc_{i}.pdf",
            "page": i,
            "section": None,
            "citation": f"doc_{i}.pdf, p. {i}",
            "score": s,
        })
    return results


# 1. Gate: top score < SCORE_THRESHOLD -> returns not-found without calling LLM
def test_below_threshold_gates_llm():
    low_score_results = _sample_context_results(scores=(0.52, 0.40))
    store = MockStore(results=low_score_results)

    llm_called = False

    def mock_llm(system_instruction, prompt):
        nonlocal llm_called
        llm_called = True
        return json.dumps({"found": True, "answer": "Should not be called", "used_sources": [1]})

    # English query
    resp_en = answer("What is the parking fee?", store=store, llm=mock_llm)
    assert not llm_called
    assert resp_en.found is False
    assert resp_en.answer == NOT_FOUND_EN
    assert resp_en.sources == []
    assert resp_en.top_score == 0.52
    assert resp_en.language == "english"

    # Roman Urdu query
    resp_roman = answer("parking kahan par hai?", store=store, llm=mock_llm)
    assert not llm_called
    assert resp_roman.found is False
    assert resp_roman.answer == NOT_FOUND_ROMAN
    assert resp_roman.language == "roman_urdu"

    # Urdu script query
    resp_urdu = answer("پارکنگ کہاں ہے؟", store=store, llm=mock_llm)
    assert not llm_called
    assert resp_urdu.found is False
    assert resp_urdu.answer == NOT_FOUND_URDU
    assert resp_urdu.language == "urdu"


# 2. Found with citations: LLM returns found=true and used_sources=[1, 3]
def test_found_with_valid_citations():
    results = _sample_context_results(scores=(0.88, 0.79, 0.72))
    store = MockStore(results=results)

    def mock_llm(system_instruction, prompt):
        assert "Context passages:" in prompt
        return json.dumps({
            "found": True,
            "answer": "Consultation fee is PKR 15,000.",
            "used_sources": [1, 3],
        })

    resp = answer("What is the consultation fee?", store=store, llm=mock_llm)
    assert resp.found is True
    assert resp.answer == "Consultation fee is PKR 15,000."
    assert len(resp.sources) == 2
    assert resp.sources[0]["citation"] == "doc_1.pdf, p. 1"
    assert resp.sources[1]["citation"] == "doc_3.pdf, p. 3"
    assert resp.sources[0]["score"] == 0.88
    assert resp.sources[1]["score"] == 0.72
    assert resp.api_calls == 2  # 1 vector query + 1 llm generation


# 3. Model hallucination guard: LLM returns found=true but used_sources=[] or invalid indices
def test_hallucination_guard_no_sources():
    results = _sample_context_results(scores=(0.85,))
    store = MockStore(results=results)

    # Empty used_sources
    def mock_llm_empty(system_instruction, prompt):
        return json.dumps({
            "found": True,
            "answer": "I hallucinated this without any source.",
            "used_sources": [],
        })

    resp1 = answer("Can I pay via JazzCash?", store=store, llm=mock_llm_empty)
    assert resp1.found is False
    assert resp1.answer == NOT_FOUND_EN
    assert resp1.sources == []

    # Out of bounds indices
    def mock_llm_out_of_bounds(system_instruction, prompt):
        return json.dumps({
            "found": True,
            "answer": "Hallucinated index.",
            "used_sources": [99],
        })

    resp2 = answer("Can I pay via JazzCash?", store=store, llm=mock_llm_out_of_bounds)
    assert resp2.found is False
    assert resp2.answer == NOT_FOUND_EN
    assert resp2.sources == []


# 4. Model found=false: answer is the not-found message
def test_model_declares_found_false():
    results = _sample_context_results(scores=(0.75,))
    store = MockStore(results=results)

    def mock_llm(system_instruction, prompt):
        return json.dumps({
            "found": False,
            "answer": "Not mentioned in context.",
            "used_sources": [],
        })

    resp = answer("Do you provide swimming pool access?", store=store, llm=mock_llm)
    assert resp.found is False
    assert resp.answer == NOT_FOUND_EN
    assert resp.sources == []


# 5. Malformed JSON handling: first call returns malformed JSON, second call returns valid JSON
def test_malformed_json_repair_retry_success():
    results = _sample_context_results(scores=(0.85,))
    store = MockStore(results=results)

    calls = 0

    def mock_llm(system_instruction, prompt):
        nonlocal calls
        calls += 1
        if calls == 1:
            return "This is not valid json {"
        return json.dumps({
            "found": True,
            "answer": "Repaired answer.",
            "used_sources": [1],
        })

    resp = answer("What is the fee?", store=store, llm=mock_llm)
    assert calls == 2
    assert resp.found is True
    assert resp.answer == "Repaired answer."
    assert resp.api_calls == 3  # 1 retrieval + 1 failed LLM + 1 repaired LLM


def test_malformed_json_repair_failure_raises_generation_error():
    results = _sample_context_results(scores=(0.85,))
    store = MockStore(results=results)

    def mock_llm(system_instruction, prompt):
        return "Malformed JSON every time {{"

    with pytest.raises(GenerationError, match="Failed to generate valid structured JSON"):
        answer("What is the fee?", store=store, llm=mock_llm)


# 6. 429 retry: simulated 429 on generate_content -> retried and succeeds
def test_generation_429_retry_then_success(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)

    attempt = 0
    fake_client = MagicMock()

    class FakeResponse:
        text = json.dumps({"found": True, "answer": "Success after 429", "used_sources": [1]})

    class RateLimitErr(Exception):
        code = 429

    def mock_generate(*args, **kwargs):
        nonlocal attempt
        attempt += 1
        if attempt == 1:
            raise RateLimitErr("429 RESOURCE_EXHAUSTED: rate limit exceeded")
        return FakeResponse()

    fake_client.models.generate_content.side_effect = mock_generate

    output = _call_gemini_with_retry(
        fake_client,
        model="gemini-3.5-flash-lite",
        system_instruction="sys",
        prompt="prompt",
        max_retries=3,
    )
    assert attempt == 2
    assert "Success after 429" in output


# 7. Language detection helper
def test_language_detection():
    # Urdu script
    assert detect_language("مشاورت کی فیس کتنی ہے؟") == "urdu"
    assert detect_language("دفتر کے اوقات کیا ہیں؟") == "urdu"

    # Roman Urdu
    assert detect_language("consultation ki fees kitni hai?") == "roman_urdu"
    assert detect_language("Saturday ko office kab tak khula hota hai?") == "roman_urdu"

    # English (even with words like 'fees' or single roman token)
    assert detect_language("What is the initial consultation fee and when is it waived?") == "english"
    assert detect_language("What are the hourly rates for each lawyer level?") == "english"
    assert detect_language("Are fees payable in advance?") == "english"
    assert detect_language("Is there a fee for legal consultation?") == "english"

    # Single roman token should NOT trigger roman urdu
    assert detect_language("Hello sir, what is the policy for client data?") == "english"


# 8. Empty vector store -> returns not-found without calling LLM
def test_empty_vector_store():
    store = MockStore(results=[], doc_count=0)
    llm_called = False

    def mock_llm(system_instruction, prompt):
        nonlocal llm_called
        llm_called = True
        return "{}"

    resp = answer("Any question?", store=store, llm=mock_llm)
    assert not llm_called
    assert resp.found is False
    assert resp.answer == NOT_FOUND_EN
    assert resp.sources == []
    assert resp.top_score == 0.0
