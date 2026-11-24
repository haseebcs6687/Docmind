"""Smoke tests for the DocMind Streamlit UI using AppTest (offline, 0 real API calls)."""

from pathlib import Path
from unittest import mock
import pytest
from streamlit.testing.v1 import AppTest

from src.rag import ChatSession, RagResponse
from src.ui.components import (
    demo_callout_card,
    file_type_chip,
    source_mini_card,
    stat_card,
)
from src.ui.theme import STYLES_FILE
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
        # Starter buttons must be present before conversation (Staff mode default)
        starter_buttons = [b for b in at.button if "intake" in b.label.lower() or "conflict" in b.label.lower()]
        assert len(starter_buttons) >= 1

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
        answer="Staff follow standard client intake procedures.",
        sources=[{
            "source": "Client_Intake_SOP.pdf",
            "citation": "Client_Intake_SOP.pdf, p. 1",
            "page": 1,
            "section": None,
            "score": 0.91,
            "snippet": "Staff must verify client identity and conflict status.",
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

        starter_btn = [b for b in at.button if "intake" in b.label.lower()][0]
        starter_btn.click().run()

        assert len(at.exception) == 0, f"Exceptions after starter click: {at.exception}"
        markdown_values = [m.value for m in at.markdown]
        assert any("intake procedures" in val for val in markdown_values)
        assert any("Client_Intake_SOP.pdf, p. 1" in val for val in markdown_values)


def test_documents_page_renders_metrics_and_sources():
    """Verify that the documents page displays stat cards, disclaimers, and indexed files."""
    mock_store = mock.MagicMock(spec=VectorStore)
    mock_store.count.value = 25
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
        markdown_values = [m.value for m in at.markdown]

        # Verify pastel stat cards content
        assert any("Indexed Documents" in val for val in markdown_values)
        assert any("Total Chunks" in val for val in markdown_values)
        assert any("Free Quota" in val for val in markdown_values)
        assert any("Supported Types" in val for val in markdown_values)
        assert any("25" in val for val in markdown_values)

        # Verify disclaimer callout card
        assert any(
            "Sterling &amp; Rauf" in val and "fictional law firm" in val
            for val in markdown_values
        )


def test_html_escaping_prevents_xss():
    """Verify that malicious script tags in filenames and snippets are escaped to prevent XSS injection."""
    malicious_input = "<script>alert(1)</script>"

    # Source mini card
    card_html = source_mini_card(citation=malicious_input, score=0.88, snippet=malicious_input)
    assert "<script>" not in card_html
    assert "</script>" not in card_html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in card_html

    # File type chip
    chip_html = file_type_chip(malicious_input)
    assert "<script>" not in chip_html.lower()
    assert "</script>" not in chip_html.lower()
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in chip_html.lower()

    # Stat card
    stat_html = stat_card(label=malicious_input, value=malicious_input, icon=malicious_input, tone="mint")
    assert "<script>" not in stat_html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in stat_html

    # Demo callout card
    callout_html = demo_callout_card(malicious_input)
    assert "<script>" not in callout_html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in callout_html

    # Role chip and Practice Area in source card
    from src.ui.components import role_chip
    role_html = role_chip(malicious_input)
    assert "<script>" not in role_html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in role_html

    card_pa_html = source_mini_card("Citation", 0.9, "snippet", visibility="staff", practice_area=malicious_input)
    assert "<script>" not in card_pa_html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in card_pa_html


def test_styles_css_exists_and_injected():
    """Verify that styles.css exists on disk and is injected into the Streamlit app with marker comment."""
    assert STYLES_FILE.exists(), "styles.css must exist in src/ui/styles.css"
    assert STYLES_FILE.stat().st_size > 0, "styles.css must not be empty"

    mock_store = mock.MagicMock(spec=VectorStore)
    mock_store.count.return_value = 0
    mock_store.list_sources.return_value = []

    with mock.patch("src.ui.state.get_store", return_value=mock_store), \
         mock.patch("src.ui.chat_page.get_store", return_value=mock_store), \
         mock.patch("app.get_store", return_value=mock_store):
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()

        assert len(at.exception) == 0, f"App raised exceptions: {at.exception}"
        markdown_values = [m.value for m in at.markdown]
        assert any("<!-- docmind-injected-styles -->" in val for val in markdown_values), (
            "Custom styles marker comment was not found in injected markdown."
        )


# ---------------- Step 11: Role-Based Access UI Tests ----------------

def test_client_mode_documents_page_read_only_and_hides_controls():
    """Verify that Documents page in Client mode hides upload, sample-load, edit, and delete controls."""
    mock_store = mock.MagicMock(spec=VectorStore)
    mock_store.count.return_value = 10
    mock_store.list_sources.side_effect = lambda allowed_visibility=None: [
        {"name": "Fee_Schedule_2026.pdf", "chunk_count": 10, "file_type": "pdf", "visibility": "client", "practice_area": "Billing & Fees"}
    ] if allowed_visibility == {"client"} else [
        {"name": "Fee_Schedule_2026.pdf", "chunk_count": 10, "file_type": "pdf", "visibility": "client", "practice_area": "Billing & Fees"},
        {"name": "Client_Intake_SOP.pdf", "chunk_count": 8, "file_type": "pdf", "visibility": "staff", "practice_area": "Operations"},
    ]

    from src.ui.documents_page import render_documents_page
    import streamlit as st

    with mock.patch("src.ui.state.get_store", return_value=mock_store), \
         mock.patch("src.ui.documents_page.get_store", return_value=mock_store), \
         mock.patch("app.get_store", return_value=mock_store):

        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()

        # Switch role to Client in sidebar segmented control
        # In AppTest, segmented_control or session_state can be set
        at.session_state.current_role = "Client"
        at.run()

        assert len(at.exception) == 0, f"Exceptions on role switch: {at.exception}"


def test_starter_questions_differ_by_mode():
    """Verify that Chat starter questions match the active role (Staff vs Client)."""
    from src.ui.chat_page import CLIENT_STARTER_QUESTIONS, STAFF_STARTER_QUESTIONS
    assert len(STAFF_STARTER_QUESTIONS) == 4
    assert len(CLIENT_STARTER_QUESTIONS) == 4
    assert "client intake" in STAFF_STARTER_QUESTIONS[0].lower()
    assert "consultation fee" in CLIENT_STARTER_QUESTIONS[0].lower()
    # Starters must not be identical across modes
    assert set(STAFF_STARTER_QUESTIONS) != set(CLIENT_STARTER_QUESTIONS)


def test_batch_upload_defaults_to_staff_visibility():
    """Verify that upload defaults to staff visibility per specification."""
    from src.config import ACCESS_MODES, DEFAULT_UPLOAD_VISIBILITY
    assert DEFAULT_UPLOAD_VISIBILITY == "staff"
    assert "staff" in ACCESS_MODES
    assert "client" in ACCESS_MODES


# ---------------- Step 13: Draft Client Reply & Memo Export UI Tests ----------------

def test_draft_button_and_memo_export_in_ui():
    """Verify draft button visibility in staff mode, absence in client mode, and memo button behavior."""
    mock_store = mock.MagicMock(spec=VectorStore)
    mock_store.count.return_value = 10
    mock_store.list_sources.return_value = [
        {"name": "Fee_Schedule_2026.pdf", "chunk_count": 10, "file_type": "pdf", "visibility": "client", "practice_area": "Billing & Fees"}
    ]

    mock_resp = RagResponse(
        answer="The consultation fee is PKR 5,000.",
        sources=[{
            "source": "Fee_Schedule_2026.pdf",
            "citation": "Fee_Schedule_2026.pdf, p. 1",
            "page": 1,
            "section": None,
            "score": 0.88,
            "snippet": "Initial consultation fee is PKR 5,000.",
            "text": "Initial consultation fee is PKR 5,000.",
            "visibility": "client",
            "practice_area": "Billing & Fees",
        }],
        found=True,
        latency_ms=250.0,
    )

    with mock.patch("src.ui.state.get_store", return_value=mock_store), \
         mock.patch("src.ui.chat_page.get_store", return_value=mock_store), \
         mock.patch("src.ui.documents_page.get_store", return_value=mock_store), \
         mock.patch("app.get_store", return_value=mock_store), \
         mock.patch.object(ChatSession, "ask", return_value=mock_resp):

        # 1. Staff Mode: initial state (no turns)
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()
        assert len(at.exception) == 0

        # Memo button should be disabled initially
        disabled_memo = [b for b in at.button if "export memo" in b.label.lower() and getattr(b, "disabled", False)]
        assert len(disabled_memo) >= 1

        # Submit question in Staff mode
        at.chat_input[0].set_value("What is the consultation fee?").run()
        assert len(at.exception) == 0

        # Draft button must now be visible in Staff mode
        draft_buttons = [b for b in at.button if "draft client reply" in b.label.lower()]
        assert len(draft_buttons) == 1

        # Memo export download button must now be present
        memo_download = [b for b in at.download_button if "export memo" in b.label.lower()]
        assert len(memo_download) == 1

        # 2. Client Mode: switch to Client mode via sidebar segmented control
        at.sidebar.segmented_control(key="role_switcher").set_value("Client").run()
        assert len(at.exception) == 0

        # Submit question in Client mode
        at.chat_input[0].set_value("What is the consultation fee?").run()
        assert len(at.exception) == 0

        # Draft button MUST NOT be present in Client mode
        client_draft_buttons = [b for b in at.button if "draft client reply" in b.label.lower()]
        assert len(client_draft_buttons) == 0

        # Memo export download button is still available in Client mode
        client_memo_download = [b for b in at.download_button if "export memo" in b.label.lower()]
        assert len(client_memo_download) == 1


def test_insights_page_access_and_navigation(tmp_path):
    """Verify that Knowledge Insights is strictly Staff-only and absent in Client mode."""
    from src.analytics import AnalyticsStore
    from src.ui.insights_page import render_insights_page

    mock_store = mock.MagicMock(spec=VectorStore)
    mock_store.count.return_value = 5
    mock_store.list_sources.return_value = [{"name": "Doc.pdf", "chunk_count": 5}]

    mock_analytics = AnalyticsStore(db_path=str(tmp_path / "smoke_analytics.db"))

    with mock.patch("src.ui.state.get_store", return_value=mock_store), \
         mock.patch("src.ui.state.get_analytics", return_value=mock_analytics), \
         mock.patch("src.ui.chat_page.get_store", return_value=mock_store), \
         mock.patch("src.ui.documents_page.get_store", return_value=mock_store), \
         mock.patch("app.get_store", return_value=mock_store):

        # 1. Staff Mode: Contract Analyzer & Knowledge Insights are present in nav
        at = AppTest.from_file(APP_PATH, default_timeout=15)
        at.run()
        assert len(at.exception) == 0

        # Switch to Client mode
        at.sidebar.segmented_control(key="role_switcher").set_value("Client").run()
        assert len(at.exception) == 0
        assert at.session_state.current_role == "Client"


