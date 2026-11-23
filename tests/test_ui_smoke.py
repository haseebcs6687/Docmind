"""Smoke tests for the DocMind Streamlit UI using AppTest (offline, 0 real API calls)."""

from pathlib import Path
from unittest import mock
import pytest
from streamlit.testing.v1 import AppTest

from src.rag import ChatSession, RagResponse
from src.vectorstore import VectorStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_PATH = str(PROJECT_ROOT / "app.py")
DOCS_PAGE_PATH = str(PROJECT_ROOT / "src" / "ui" / "documents_page.py")


def test_empty_store_renders_empty_state():
    """Verify that an empty vector store displays the empty-state notice and no chat input."""
    mock_store = mock.MagicMock(spec=VectorStore)
    mock_store.count.return_value = 0
    mock_store.list_sources.return_value = []

    with mock.patch("src.ui.state.get_store", return_value=mock_store), \
         mock.patch("src.ui.chat_page.get_store", return_value=mock_store), \
         mock.patch("src.ui.documents_page.get_store", return_value=mock_store), \
         mock.patch("app.get_store", return_value=mock_store):
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()

        assert len(at.exception) == 0, f"App raised exceptions: {at.exception}"
        # Empty state info message should be shown
        assert len(at.info) >= 1
        assert "No documents are currently indexed" in at.info[0].value
        # No chat input should be present when store is empty
        assert len(at.chat_input) == 0


def test_populated_store_renders_starters_and_runs_chat():
    """Verify that a populated vector store renders starter buttons and answers questions with citations."""
    mock_store = mock.MagicMock(spec=VectorStore)
    mock_store.count.return_value = 10
    mock_store.list_sources.return_value = [
        {"name": "Fee_Schedule_2026.pdf", "chunk_count": 10, "file_type": "pdf"}
    ]

    mock_response = RagResponse(
        answer="The initial consultation fee is PKR 5,000 for up to 45 minutes.",
        sources=[{
            "source": "Fee_Schedule_2026.pdf",
            "citation": "Fee_Schedule_2026.pdf, p. 2",
            "page": 2,
            "section": None,
            "score": 0.94,
            "snippet": "Initial consultation fee is PKR 5,000 for up to 45 minutes.",
        }],
        found=True,
        latency_ms=380.0,
    )

    with mock.patch("src.ui.state.get_store", return_value=mock_store), \
         mock.patch("src.ui.chat_page.get_store", return_value=mock_store), \
         mock.patch("src.ui.documents_page.get_store", return_value=mock_store), \
         mock.patch("app.get_store", return_value=mock_store), \
         mock.patch.object(ChatSession, "ask", return_value=mock_response):
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()

        assert len(at.exception) == 0, f"App raised exceptions: {at.exception}"
        # Chat input must be available
        assert len(at.chat_input) == 1
        # Starter buttons must be present before conversation
        starter_buttons = [b for b in at.button if "consultation" in b.label.lower()]
        assert len(starter_buttons) == 1

        # Submit question via chat input
        at.chat_input[0].set_value("What is the initial consultation fee?").run()

        assert len(at.exception) == 0, f"Exceptions after chat: {at.exception}"
        # Verify assistant answer and citation rendered in markdown
        markdown_values = [m.value for m in at.markdown]
        assert any("PKR 5,000" in val for val in markdown_values)
        assert any("Fee_Schedule_2026.pdf, p. 2" in val for val in markdown_values)
        assert any("94%" in val for val in markdown_values)


def test_populated_store_starter_button_click():
    """Verify that clicking a starter question triggers search and renders the answer."""
    mock_store = mock.MagicMock(spec=VectorStore)
    mock_store.count.return_value = 10
    mock_store.list_sources.return_value = [
        {"name": "Fee_Schedule_2026.pdf", "chunk_count": 10, "file_type": "pdf"}
    ]

    mock_response = RagResponse(
        answer="Late invoice payments incur a 2% monthly surcharge.",
        sources=[{
            "source": "Fee_Schedule_2026.pdf",
            "citation": "Fee_Schedule_2026.pdf, p. 3",
            "page": 3,
            "section": None,
            "score": 0.91,
            "snippet": "Invoices unpaid after 30 days incur a 2% monthly surcharge.",
        }],
        found=True,
        latency_ms=250.0,
    )

    with mock.patch("src.ui.state.get_store", return_value=mock_store), \
         mock.patch("src.ui.chat_page.get_store", return_value=mock_store), \
         mock.patch("src.ui.documents_page.get_store", return_value=mock_store), \
         mock.patch("app.get_store", return_value=mock_store), \
         mock.patch.object(ChatSession, "ask", return_value=mock_response):
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()

        starter_btn = [b for b in at.button if "invoice" in b.label.lower()][0]
        starter_btn.click().run()

        assert len(at.exception) == 0, f"Exceptions after starter click: {at.exception}"
        markdown_values = [m.value for m in at.markdown]
        assert any("Late invoice payments" in val for val in markdown_values)
        assert any("Fee_Schedule_2026.pdf, p. 3" in val for val in markdown_values)


def test_documents_page_renders_metrics_and_sources():
    """Verify that the documents page displays metrics, disclaimers, and indexed files."""
    mock_store = mock.MagicMock(spec=VectorStore)
    mock_store.count.return_value = 25
    mock_store.list_sources.return_value = [
        {"name": "Fee_Schedule_2026.pdf", "chunk_count": 15, "file_type": "pdf"},
        {"name": "Client_FAQ.txt", "chunk_count": 10, "file_type": "txt"},
    ]

    with mock.patch("src.ui.state.get_store", return_value=mock_store), \
         mock.patch("src.ui.documents_page.get_store", return_value=mock_store), \
         mock.patch("app.get_store", return_value=mock_store):
        at = AppTest.from_file(DOCS_PAGE_PATH, default_timeout=15)
        at.run()

        assert len(at.exception) == 0, f"Documents page exceptions: {at.exception}"
        # Metrics check
        metric_labels = [m.label for m in at.metric]
        assert "Indexed Documents" in metric_labels
        assert "Total Chunks" in metric_labels

        metric_vals = [m.value for m in at.metric]
        assert 2 in metric_vals or "2" in metric_vals
        assert 25 in metric_vals or "25" in metric_vals

        # Disclaimers
        assert any("Sterling & Rauf Law Associates is a fictional law firm" in info.value for info in at.info)
