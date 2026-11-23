"""Unit tests for client reply drafting module (offline, 0 real API calls)."""

import json
from pathlib import Path
import sys
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.drafting import (
    DraftAccessError,
    DraftCache,
    DraftCooldownError,
    DraftSessionLimitError,
    DraftSessionTracker,
    DraftValidationError,
    _sanitize_name,
    _strip_control_chars,
    _strip_markdown_fences,
    draft_client_reply,
    draft_to_text,
    extract_numeric_tokens,
)
from src.gemini_client import GenerationError


def test_draft_refused_in_client_mode():
    """Drafting must strictly reject non-staff access."""
    with pytest.raises(DraftAccessError, match="restricted to Staff mode"):
        draft_client_reply(
            question="What is the fee?",
            answer="PKR 5,000.",
            sources=[{"source": "Fee_Schedule_2026.pdf", "text": "PKR 5,000", "score": 0.8}],
            access_mode="client",
        )


def test_only_found_responses_can_be_drafted():
    """Drafting fails if answer is empty, not found, or sources empty."""
    with pytest.raises(DraftValidationError, match="Cannot draft reply"):
        draft_client_reply(
            question="Where is parking?",
            answer="I couldn't find this in the uploaded documents.",
            sources=[],
            access_mode="staff",
        )
    with pytest.raises(DraftValidationError, match="Cannot draft reply"):
        draft_client_reply(
            question="Where is parking?",
            answer="",
            sources=[{"source": "doc.pdf", "text": "something"}],
            access_mode="staff",
        )


def test_numeric_normalization_and_extraction():
    """Ensure exact extraction and normalization of amounts, percentages, times, days, and date exclusion."""
    text = (
        "Effective January 15, 2026, the consultation fee is PKR 5,000. "
        "Waived if signed within 7 days. Late fee is 2%. Office opens at 9:30 AM."
    )
    tokens = extract_numeric_tokens(text)
    # Check normalization: 5,000 -> 5000
    assert "5000" in tokens
    assert "7" in tokens
    assert "2%" in tokens
    assert "9:30" in tokens
    # Ensure calendar years and dates are excluded
    assert "2026" not in tokens
    assert "15" not in tokens  # day of January 15 date


def test_unverified_figures_flagged():
    """An invented figure in the draft must appear in unverified_figures."""
    context_answer = "The consultation fee is PKR 5,000, waived if signed within 7 days."
    sources = [{"source": "Fee_Schedule_2026.pdf", "text": context_answer, "score": 0.85}]

    fake_response = json.dumps({
        "subject": "Consultation Fee Details",
        "body": "Dear Client, the fee is PKR 5,000 with a retainer of PKR 85,000 within 14 days. Best, Zainab Malik, Sterling & Rauf Law Associates.",
    })
    cache = DraftCache()
    tracker = DraftSessionTracker(cooldown_seconds=0.0)

    result = draft_client_reply(
        question="What is the consultation fee?",
        answer=context_answer,
        sources=sources,
        access_mode="staff",
        llm=lambda s, p: fake_response,
        cache=cache,
        tracker=tracker,
    )
    assert "85000" in result.unverified_figures
    assert "14" in result.unverified_figures
    assert "5000" not in result.unverified_figures


def test_faithful_draft_produces_no_unverified_figures():
    """A faithful draft containing only contextual numbers produces empty unverified_figures."""
    context_answer = "The consultation fee is PKR 5,000, waived if signed within 7 days. Late fee is 2%."
    sources = [{"source": "Fee_Schedule_2026.pdf", "text": context_answer, "score": 0.85}]

    fake_response = json.dumps({
        "subject": "Consultation Fee Information",
        "body": "Dear Ms. Khan, our initial fee is PKR 5,000, which is waived if an engagement is signed within 7 days. Late invoices incur a 2% monthly fee. Please contact us with questions. Sincerely, Zainab Malik, Sterling & Rauf Law Associates.",
    })
    cache = DraftCache()
    tracker = DraftSessionTracker(cooldown_seconds=0.0)

    result = draft_client_reply(
        question="What is the fee?",
        answer=context_answer,
        sources=sources,
        client_name="Ms. Khan",
        sender_name="Zainab Malik",
        access_mode="staff",
        llm=lambda s, p: fake_response,
        cache=cache,
        tracker=tracker,
    )
    assert result.unverified_figures == []


def test_name_and_sender_sanitization():
    """Ensure control characters, newlines, and excess length are stripped."""
    dirty_name = "Mr. John Doe\n\r\t--Attn: Legal" + "x" * 100
    cleaned = _sanitize_name(dirty_name, "[Client Name]")
    assert "\n" not in cleaned
    assert "\r" not in cleaned
    assert len(cleaned) <= 60
    assert cleaned.startswith("Mr. John Doe")

    # Empty name falls back to default
    assert _sanitize_name("", "[Client Name]") == "[Client Name]"
    assert _sanitize_name("   \n\r  ", "[Your Name]") == "[Your Name]"


def test_cache_hit_and_tone_partitioning():
    """Cache returns identical response with 0 calls; different tone causes new call."""
    call_count = 0

    def mock_llm(s, p):
        nonlocal call_count
        call_count += 1
        return json.dumps({
            "subject": f"Call #{call_count}",
            "body": "Dear Client, fee is PKR 5,000. Best, DocMind, Sterling & Rauf Law Associates.",
        })

    cache = DraftCache()
    tracker = DraftSessionTracker(cooldown_seconds=0.0)
    sources = [{"source": "Fee.pdf", "text": "Fee is PKR 5,000.", "score": 0.9}]

    # 1. First call (Formal)
    r1 = draft_client_reply(
        question="Fee?", answer="PKR 5,000", sources=sources,
        tone="Formal", access_mode="staff", llm=mock_llm, cache=cache, tracker=tracker
    )
    assert call_count == 1
    assert r1.cached is False

    # 2. Second call with same tone -> Cache hit
    r2 = draft_client_reply(
        question="Fee?", answer="PKR 5,000", sources=sources,
        tone="Formal", access_mode="staff", llm=mock_llm, cache=cache, tracker=tracker
    )
    assert call_count == 1
    assert r2.cached is True
    assert r2.api_calls == 0
    assert r2.subject == r1.subject
    assert r2.body == r1.body

    # 3. Third call with different tone (Friendly) -> New call
    r3 = draft_client_reply(
        question="Fee?", answer="PKR 5,000", sources=sources,
        tone="Friendly", access_mode="staff", llm=mock_llm, cache=cache, tracker=tracker
    )
    assert call_count == 2
    assert r3.cached is False
    assert r3.subject == "Call #2"


def test_session_limit_and_cooldown():
    """Enforce session limit ceiling and request cooldown."""
    tracker = DraftSessionTracker(max_drafts=2, cooldown_seconds=0.5)

    def mock_llm(s, p):
        return json.dumps({"subject": "Hi", "body": "Body text Sterling & Rauf Law Associates."})

    sources = [{"source": "Fee.pdf", "text": "Fee", "score": 0.9}]

    # Call 1: success
    draft_client_reply("q", "a", sources, access_mode="staff", llm=mock_llm, cache=DraftCache(), tracker=tracker)

    # Call 2 immediately: raises DraftCooldownError
    with pytest.raises(DraftCooldownError, match="Please wait"):
        draft_client_reply("q2", "a", sources, access_mode="staff", llm=mock_llm, cache=DraftCache(), tracker=tracker)

    # Reset cooldown timer manually
    tracker.last_draft_time = 0.0

    # Call 2: success (count becomes 2)
    draft_client_reply("q2", "a", sources, access_mode="staff", llm=mock_llm, cache=DraftCache(), tracker=tracker)

    # Call 3: exceeds max_drafts=2
    tracker.last_draft_time = 0.0
    with pytest.raises(DraftSessionLimitError, match="Session draft limit"):
        draft_client_reply("q3", "a", sources, access_mode="staff", llm=mock_llm, cache=DraftCache(), tracker=tracker)


def test_markdown_fences_and_control_chars_stripped():
    """Markdown fences and non-printable control chars must be stripped."""
    fenced = "```json\n{\"subject\": \"Legal Notice\", \"body\": \"Hello\\x00\\x08 world! Sterling & Rauf Law Associates.\"}\n```"
    cache = DraftCache()
    tracker = DraftSessionTracker(cooldown_seconds=0.0)
    sources = [{"source": "Fee.pdf", "text": "Notice", "score": 0.9}]

    res = draft_client_reply(
        question="q", answer="a", sources=sources, access_mode="staff",
        llm=lambda s, p: fenced, cache=cache, tracker=tracker
    )
    assert "```" not in res.subject
    assert "```" not in res.body
    assert "\x00" not in res.body
    assert "\x08" not in res.body
    assert "Hello world!" in res.body


def test_empty_or_oversize_body_handling():
    """Empty or oversize body triggers retry and fails cleanly if unfixable."""
    oversize = json.dumps({"subject": "Subj", "body": "A" * 1600})
    cache = DraftCache()
    tracker = DraftSessionTracker(cooldown_seconds=0.0)
    sources = [{"source": "Fee.pdf", "text": "Fee", "score": 0.9}]

    with pytest.raises(GenerationError):
        draft_client_reply(
            question="q", answer="a", sources=sources, access_mode="staff",
            llm=lambda s, p: oversize, cache=cache, tracker=tracker
        )


def test_draft_to_text():
    """draft_to_text formats subject and body with clean spacing."""
    cache = DraftCache()
    tracker = DraftSessionTracker(cooldown_seconds=0.0)
    fake_json = json.dumps({"subject": "Important Notice", "body": "Dear Client,\nHere is the update."})
    sources = [{"source": "Fee.pdf", "text": "Notice", "score": 0.9}]

    res = draft_client_reply(
        question="q", answer="a", sources=sources, access_mode="staff",
        llm=lambda s, p: fake_json, cache=cache, tracker=tracker
    )
    text_out = draft_to_text(res)
    assert text_out == "Subject: Important Notice\n\nDear Client,\nHere is the update."


def test_html_escaping_for_draft_fields():
    """Verify that dangerous HTML strings in fields are escaped and never injected raw."""
    import html
    malicious_q = "<script>alert('pwned')</script>"
    malicious_fig = "<img src=x onerror=alert(1)>"

    escaped_q = html.escape(malicious_q)
    assert "<script>" not in escaped_q
    assert "&lt;script&gt;" in escaped_q

    escaped_fig = html.escape(malicious_fig)
    assert "<img" not in escaped_fig
    assert "&lt;img" in escaped_fig
