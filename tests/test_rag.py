"""Unit tests for the DocMind RAG pipeline, guardrails, and chat sessions."""

import json
from unittest.mock import MagicMock
import pytest

from src.rag import (
    ChatSession,
    GLOBAL_ANSWER_CACHE,
    GenerationError,
    RagResponse,
    _call_gemini_with_retry,
    answer,
    check_small_talk,
    NOT_FOUND,
)


@pytest.fixture(autouse=True)
def clear_rag_cache():
    """Ensure global answer cache is empty before each unit test."""
    GLOBAL_ANSWER_CACHE.clear()
    yield
    GLOBAL_ANSWER_CACHE.clear()


class MockStore:
    """Mock VectorStore for deterministic unit testing without ChromaDB or Gemini API."""

    def __init__(self, results=None, doc_count=5):
        self.results = results if results is not None else []
        self._doc_count = doc_count
        self.last_query = None
        self.last_allowed_visibility = None
        self.last_practice_areas = None

    def query(self, question, k=5, allowed_visibility=None, practice_areas=None, **kwargs):
        self.last_query = question
        self.last_allowed_visibility = allowed_visibility
        self.last_practice_areas = practice_areas
        filtered = self.results
        if allowed_visibility is not None:
            filtered = [r for r in filtered if r.get("visibility", "client") in allowed_visibility]
        if practice_areas:
            filtered = [r for r in filtered if r.get("practice_area") in practice_areas]
        return filtered

    def count(self):
        return self._doc_count

    def get_fingerprint(self):
        return "mock_fp_123"


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

    resp = answer("What is the parking fee?", store=store, llm=mock_llm)
    assert not llm_called
    assert resp.found is False
    assert resp.answer == NOT_FOUND
    assert resp.sources == []
    assert resp.top_score == 0.52


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
    assert resp1.answer == NOT_FOUND
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
    assert resp2.answer == NOT_FOUND
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
    assert resp.answer == NOT_FOUND
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


# 7. Empty vector store -> returns not-found without calling LLM
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
    assert resp.answer == NOT_FOUND
    assert resp.sources == []
    assert resp.top_score == 0.0


# 8. Used sources precision instruction present in system prompt
def test_used_sources_precision_instruction_in_system_prompt():
    results = _sample_context_results(scores=(0.85,))
    store = MockStore(results=results)

    captured_system_instruction = ""

    def mock_llm(system_instruction, prompt):
        nonlocal captured_system_instruction
        captured_system_instruction = system_instruction
        return json.dumps({"found": True, "answer": "OK", "used_sources": [1]})

    answer("What is the fee?", store=store, llm=mock_llm)
    assert "In used_sources, list ONLY passages that directly state a fact used in the answer" in captured_system_instruction


# ---------------- Part D & E Tests: ChatSession & Follow-up Rewriting ----------------

# 9. Small-talk replies make 0 calls and don't swallow substantive questions
def test_small_talk_handler_makes_zero_calls():
    session = ChatSession()

    for phrase in ["hi", "Hello!", "Good morning", "thanks", "thank you so much", "bye", "what can you do"]:
        resp = session.ask(phrase)
        assert resp.found is True
        assert resp.api_calls == 0
        assert resp.sources == []
        assert len(resp.answer) > 0


def test_small_talk_does_not_swallow_real_questions():
    # Questions that start with greeting words must NOT be swallowed by small talk
    assert check_small_talk("Hi, what are your office hours?") is None
    assert check_small_talk("Hello, how much is the consultation fee?") is None
    assert check_small_talk("Good morning, do you handle corporate matters?") is None
    assert check_small_talk("Thanks, but what is the retainer fee?") is None


# 10. Rewrite is NOT called with empty history
def test_rewrite_not_called_with_empty_history():
    results = _sample_context_results(scores=(0.88,))
    store = MockStore(results=results)

    rewrite_called = False

    def mock_llm(sys_inst, prompt):
        nonlocal rewrite_called
        if "query reformulation" in (sys_inst or "") or "Standalone Question:" in prompt:
            rewrite_called = True
            return "Rewritten question"
        return json.dumps({"found": True, "answer": "Answer 1", "used_sources": [1]})

    session = ChatSession(store=store, llm=mock_llm)
    resp = session.ask("What is the consultation fee?")

    assert not rewrite_called
    assert resp.standalone_question == "What is the consultation fee?"
    assert resp.api_calls == 2  # 1 embed + 1 generation


# 11. Rewrite IS called with history and output is used for retrieval
def test_rewrite_called_with_history_and_used_for_retrieval():
    results = _sample_context_results(scores=(0.88,))
    store = MockStore(results=results)

    call_types = []

    def mock_llm(sys_inst, prompt):
        if "Standalone Question:" in prompt:
            call_types.append("rewrite")
            return "What are the hourly rates for a paralegal?"
        call_types.append("generation")
        return json.dumps({"found": True, "answer": "Paralegal rate is PKR 4,000/hr.", "used_sources": [1]})

    session = ChatSession(store=store, llm=mock_llm)

    # Turn 1: Initial question
    resp1 = session.ask("What are the hourly rates for each lawyer level?")
    assert resp1.found is True
    assert len(session.history) == 1

    # Turn 2: Follow-up question requiring rewrite
    resp2 = session.ask("And what about the paralegal?")
    assert "rewrite" in call_types
    assert resp2.standalone_question == "What are the hourly rates for a paralegal?"
    assert store.last_query == "What are the hourly rates for a paralegal?"
    assert resp2.api_calls == 3  # 1 rewrite + 1 embed + 1 generation


# 12. Invalid, too-long, or failed rewrite falls back to original question
def test_rewrite_failure_falls_back_to_original_question():
    results = _sample_context_results(scores=(0.88,))
    store = MockStore(results=results)

    rewrite_mode = "error"

    def mock_llm(sys_inst, prompt):
        if "Standalone Question:" in prompt:
            if rewrite_mode == "error":
                raise Exception("Network error during rewrite")
            elif rewrite_mode == "too_long":
                return "This is a ridiculously long rewritten question " * 20  # > 300 chars
            elif rewrite_mode == "empty":
                return ""
        return json.dumps({"found": True, "answer": "Fallback answered.", "used_sources": [1]})

    session = ChatSession(store=store, llm=mock_llm)
    session.history.append(("What are the hourly rates?", "Senior partner is 25,000/hr."))

    # Case A: Rewrite raises exception
    rewrite_mode = "error"
    resp_err = session.ask("And the paralegal?")
    assert resp_err.standalone_question == "And the paralegal?"
    assert store.last_query == "And the paralegal?"

    # Case B: Rewrite too long
    rewrite_mode = "too_long"
    resp_long = session.ask("And the paralegal?")
    assert resp_long.standalone_question == "And the paralegal?"

    # Case C: Rewrite empty
    rewrite_mode = "empty"
    resp_empty = session.ask("And the paralegal?")
    assert resp_empty.standalone_question == "And the paralegal?"


# 13. History keeps only last HISTORY_TURNS turns and excludes not-found turns
def test_history_capping_and_not_found_exclusion():
    results_found = _sample_context_results(scores=(0.88,))
    results_not_found = _sample_context_results(scores=(0.50,))  # below 0.65 threshold
    store = MockStore(results=results_found)

    def mock_llm(sys_inst, prompt):
        if "Standalone Question:" in prompt:
            lines = prompt.splitlines()
            for line in lines:
                if line.startswith("Follow-up Question:"):
                    return line.split(":", 1)[1].strip()
            return "Rewritten question"
        return json.dumps({"found": True, "answer": "Found answer.", "used_sources": [1]})

    session = ChatSession(store=store, llm=mock_llm, history_turns=3)

    # 4 successful turns -> history should only retain the last 3
    for i in range(1, 5):
        session.ask(f"Question {i}")
    assert len(session.history) == 3
    assert session.history[0][0] == "Question 2"
    assert session.history[2][0] == "Question 4"

    # Turn with not-found result -> must NOT be added to history
    store.results = results_not_found
    resp_nf = session.ask("Out of scope question")
    assert resp_nf.found is False
    assert len(session.history) == 3
    assert "Out of scope question" not in [h[0] for h in session.history]


# 14. Reset clears session history
def test_session_reset():
    session = ChatSession()
    session.history.append(("Q1", "A1"))
    assert len(session.history) == 1
    session.reset()
    assert len(session.history) == 0


# 15. Two sessions don't share state
def test_two_sessions_do_not_share_state():
    s1 = ChatSession()
    s2 = ChatSession()

    s1.history.append(("S1 Question", "S1 Answer"))
    assert len(s1.history) == 1
    assert len(s2.history) == 0


# ---------------- Step 11: Cache Precision, Citation Cap, and Access Modes ----------------

def test_cache_hit_returns_identical_text_and_sources_with_zero_calls():
    """Verify that repeat queries hit cache with identical text, sources, and api_calls=0."""
    from src.rag import AnswerCache
    results = _sample_context_results(scores=(0.90, 0.80))
    store = MockStore(results=results)

    llm_call_count = 0
    def mock_llm(sys_inst, prompt):
        nonlocal llm_call_count
        llm_call_count += 1
        return json.dumps({
            "found": True,
            "answer": "Consultation fee is PKR 5,000.",
            "used_sources": [1, 2],
        })

    # Clear global cache before test
    GLOBAL_ANSWER_CACHE.clear()

    q = "What is the consultation fee?"
    # First call - cache miss
    resp1 = answer(q, store=store, llm=mock_llm)
    assert resp1.cached is False
    assert resp1.api_calls == 2
    assert llm_call_count == 1
    assert len(resp1.sources) == 2

    # Second call with slightly different casing/whitespace - cache hit
    resp2 = answer("  what is the consultation fee?  ", store=store, llm=mock_llm)
    assert resp2.cached is True
    assert resp2.api_calls == 0
    assert resp2.latency_ms == 0.0
    assert llm_call_count == 1  # LLM must not be called again
    assert resp2.answer == resp1.answer
    assert resp2.sources == resp1.sources


def test_citation_precision_caps_at_max_citations_sorted_by_score():
    """Verify that used citations are capped at MAX_CITATIONS (3) and sorted descending by score."""
    from src.config import MAX_CITATIONS
    assert MAX_CITATIONS == 3

    # 5 passages with varying scores
    results = [
        {"id": "c1", "text": "P1", "source": "d1.pdf", "citation": "d1.pdf, p. 1", "score": 0.70},
        {"id": "c2", "text": "P2", "source": "d2.pdf", "citation": "d2.pdf, p. 2", "score": 0.95},
        {"id": "c3", "text": "P3", "source": "d3.pdf", "citation": "d3.pdf, p. 3", "score": 0.80},
        {"id": "c4", "text": "P4", "source": "d4.pdf", "citation": "d4.pdf, p. 4", "score": 0.85},
        {"id": "c5", "text": "P5", "source": "d5.pdf", "citation": "d5.pdf, p. 5", "score": 0.90},
    ]
    store = MockStore(results=results)

    def mock_llm(sys_inst, prompt):
        # LLM cites all 5
        return json.dumps({
            "found": True,
            "answer": "Answer based on multiple sources.",
            "used_sources": [1, 2, 3, 4, 5],
        })

    resp = answer("Broad legal question", store=store, llm=mock_llm, skip_cache=True)
    assert resp.found is True
    assert len(resp.sources) == 3
    # Scores must be sorted descending: 0.95, 0.90, 0.85
    scores = [s["score"] for s in resp.sources]
    assert scores == [0.95, 0.90, 0.85]
    assert resp.sources[0]["citation"] == "d2.pdf, p. 2"
    assert resp.sources[1]["citation"] == "d5.pdf, p. 5"
    assert resp.sources[2]["citation"] == "d4.pdf, p. 4"


def test_cache_key_differs_by_access_mode_and_practice_area():
    """Verify that cache isolates answers across access modes and practice area filters."""
    from src.rag import AnswerCache
    cache = AnswerCache()
    sample_resp = RagResponse(
        answer="Role-specific answer",
        sources=[{"source": "test.pdf", "citation": "test.pdf, p. 1", "score": 0.9}],
        found=True,
    )

    cache.set("intake procedure", "fp1", sample_resp, access_mode="staff", practice_areas=None)

    # Hit with same mode
    hit = cache.get("intake procedure", "fp1", access_mode="staff", practice_areas=None)
    assert hit is not None

    # Miss with client mode
    miss_mode = cache.get("intake procedure", "fp1", access_mode="client", practice_areas=None)
    assert miss_mode is None

    # Miss with practice area filter
    miss_pa = cache.get("intake procedure", "fp1", access_mode="staff", practice_areas=["Operations"])
    assert miss_pa is None


def test_client_mode_never_sends_staff_chunks_to_llm():
    """Verify that in client mode, staff-only documents are filtered out before reaching the LLM."""
    results = [
        {"id": "c1", "text": "INTERNAL ONLY STAFF INTAKE", "source": "SOP.pdf", "citation": "SOP.pdf, p. 1", "score": 0.95, "visibility": "staff"},
        {"id": "c2", "text": "PUBLIC CLIENT TERMS", "source": "Fee.pdf", "citation": "Fee.pdf, p. 1", "score": 0.85, "visibility": "client"},
    ]
    store = MockStore(results=results)

    llm_prompt_seen = []
    def mock_llm(sys_inst, prompt):
        llm_prompt_seen.append(prompt)
        return json.dumps({
            "found": True,
            "answer": "Public client terms explained.",
            "used_sources": [1],
        })

    session = ChatSession(store=store, llm=mock_llm, access_mode="client")
    resp = session.ask("Explain intake procedures", skip_cache=True)

    assert len(llm_prompt_seen) == 1
    assert "INTERNAL ONLY STAFF INTAKE" not in llm_prompt_seen[0]
    assert "PUBLIC CLIENT TERMS" in llm_prompt_seen[0]
    assert resp.found is True


def test_switching_mode_resets_history():
    """Verify that switching access modes creates fresh isolated sessions without history bleed."""
    s_staff = ChatSession(access_mode="staff")
    s_staff.history.append(("Staff Q", "Staff A"))

    s_client = ChatSession(access_mode="client")
    assert len(s_client.history) == 0
    assert len(s_staff.history) == 1

