"""Unit tests for research memo export module (offline, python-docx only, 0 API calls)."""

from datetime import datetime, timezone
import io
from pathlib import Path
import sys
import docx
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.memo import (
    MemoGenerationError,
    build_memo_docx,
    memo_filename,
    strip_invalid_xml_chars,
)


def test_memo_filename_format():
    """memo_filename returns docmind-memo-YYYYMMDD.docx."""
    dt = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)
    assert memo_filename(dt) == "docmind-memo-20261124.docx"


def test_strip_invalid_xml_chars():
    """Illegal XML 1.0 characters like NULL, bell, form feed are stripped."""
    dirty = "Hello\x00\x07\x0b\x0c World!\nTabs\tand standard newlines preserved."
    cleaned = strip_invalid_xml_chars(dirty)
    assert "\x00" not in cleaned
    assert "\x07" not in cleaned
    assert "\x0b" not in cleaned
    assert "\x0c" not in cleaned
    assert "Hello World!" in cleaned
    assert "\t" in cleaned
    assert "\n" in cleaned


def test_memo_generation_and_docx_structure():
    """Generated DOCX must open cleanly with python-docx and contain all expected sections."""
    messages = [
        {"role": "user", "content": "What is the initial consultation fee?"},
        {
            "role": "assistant",
            "question": "What is the initial consultation fee?",
            "content": "The firm charges PKR 5,000 for a 45-minute consultation.",
            "found": True,
            "sources": [
                {
                    "source": "Fee_Schedule_2026.pdf",
                    "citation": "Fee_Schedule_2026.pdf, p. 1",
                    "score": 0.784,
                    "snippet": "Initial consultation fee is PKR 5,000 for 45 minutes.",
                }
            ],
        },
        {"role": "user", "content": "Do you offer criminal defense?"},
        {
            "role": "assistant",
            "question": "Do you offer criminal defense?",
            "content": "I couldn't find this in the uploaded documents.",
            "found": False,
            "sources": [],
        },
    ]

    fixed_time = datetime(2026, 11, 24, 14, 30, 0, tzinfo=timezone.utc)
    docx_bytes = build_memo_docx(
        messages=messages,
        access_mode="staff",
        generated_on=fixed_time,
    )
    assert len(docx_bytes) > 1000

    # Reopen with python-docx
    doc = docx.Document(io.BytesIO(docx_bytes))

    # Core properties
    assert doc.core_properties.title == "Research Memo"
    assert doc.core_properties.author == "DocMind"

    # Headings check
    headings = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
    assert "Research Memo" in headings
    assert "Findings" in headings
    assert "Q1. What is the initial consultation fee?" in headings
    assert "Open items" in headings

    # Table metadata check
    assert len(doc.tables) >= 1
    table = doc.tables[0]
    table_dict = {table.cell(i, 0).text: table.cell(i, 1).text for i in range(len(table.rows))}
    assert table_dict["Date"] == "November 24, 2026"
    assert table_dict["Prepared by"] == "DocMind assistant (draft)"
    assert table_dict["View"] == "Staff view"
    assert table_dict["Questions answered"] == "1"

    # Text content check
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "PKR 5,000 for a 45-minute consultation" in full_text
    assert "Fee_Schedule_2026.pdf, p. 1 (78% match)" in full_text
    assert "Do you offer criminal defense? — Not found in the uploaded documents" in full_text
    assert "This is not legal advice. Fictional demo data." in full_text


def test_small_talk_excluded_from_memo():
    """Small talk greetings/thanks must not appear in Findings or Open items."""
    messages = [
        {"role": "user", "content": "Hello!"},
        {
            "role": "assistant",
            "question": "Hello!",
            "content": "Hello! How can I assist you with your legal documents today?",
            "found": False,
            "sources": [],
        },
        {"role": "user", "content": "What are your office hours?"},
        {
            "role": "assistant",
            "question": "What are your office hours?",
            "content": "Office hours are Monday to Friday 9:30 AM to 5:30 PM.",
            "found": True,
            "sources": [{"source": "Client_FAQ.txt", "label": "Client_FAQ.txt", "score": 0.8, "snippet": "Hours 9:30"}],
        },
    ]

    docx_bytes = build_memo_docx(messages=messages, access_mode="client")
    doc = docx.Document(io.BytesIO(docx_bytes))
    full_text = "\n".join(p.text for p in doc.paragraphs)

    assert "office hours" in full_text.lower()
    assert "Hello!" not in full_text


def test_memo_with_no_answered_turns_raises_error():
    """If no questions were answered (e.g. only greetings or not-found), raises MemoGenerationError."""
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "question": "Hello", "content": "Hi there!", "found": False, "sources": []},
    ]
    with pytest.raises(MemoGenerationError, match="No answered questions"):
        build_memo_docx(messages=messages, access_mode="staff")


def test_memo_truncation_to_last_40_turns():
    """Conversation history beyond 40 turns is truncated to the most recent 40 turns."""
    messages = []
    for i in range(50):
        messages.append({"role": "user", "content": f"Question {i}?"})
        messages.append({
            "role": "assistant",
            "question": f"Question {i}?",
            "content": f"Answer {i}",
            "found": True,
            "sources": [{"source": "doc.pdf", "label": "doc.pdf", "score": 0.7, "snippet": f"snip {i}"}],
        })

    docx_bytes = build_memo_docx(messages=messages, access_mode="staff")
    doc = docx.Document(io.BytesIO(docx_bytes))
    full_text = "\n".join(p.text for p in doc.paragraphs)

    # 40 turns of (user+asst) means 20 Q&A pairs (questions 30 to 49)
    assert "Question 49?" in full_text
    assert "Question 0?" not in full_text


def test_client_memo_contains_only_session_content():
    """Client memo contains strictly what was displayed in the client session."""
    client_messages = [
        {"role": "user", "content": "What is the consultation fee?"},
        {
            "role": "assistant",
            "question": "What is the consultation fee?",
            "content": "PKR 5,000.",
            "found": True,
            "sources": [{"source": "Fee_Schedule_2026.pdf", "label": "Fee_Schedule_2026.pdf", "score": 0.8, "snippet": "5,000"}],
        },
    ]
    docx_bytes = build_memo_docx(messages=client_messages, access_mode="client")
    doc = docx.Document(io.BytesIO(docx_bytes))
    full_text = "\n".join(p.text for p in doc.paragraphs)

    assert len(doc.tables) >= 1
    table = doc.tables[0]
    table_dict = {table.cell(i, 0).text: table.cell(i, 1).text for i in range(len(table.rows))}
    assert table_dict["View"] == "Client view"
    assert "Fee_Schedule_2026.pdf" in full_text
    # Proves staff documents are completely absent
    assert "Master_Services_Agreement" not in full_text
    assert "Commercial_Lease" not in full_text
    assert "Client_Intake_SOP" not in full_text
    assert "Confidentiality_and_Data_Policy" not in full_text
