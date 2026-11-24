"""DocMind - Streamlit Knowledge Agent Entrypoint."""

import sys
from pathlib import Path
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DEMO_MODE, check_storage_writable
from src.logging_setup import configure_logging
from src.ui.chat_page import render_chat_page
from src.ui.components import brand_header, sidebar_status_chip
from src.ui.contracts_page import render_contracts_page
from src.ui.documents_page import render_documents_page
from src.ui.insights_page import render_insights_page
from src.ui.state import clear_chat, get_store
from src.ui.theme import inject_custom_theme

# Configure server-side logging
configure_logging()

# Streamlit Page Configuration
st.set_page_config(
    page_title="DocMind",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject custom dashboard styles once globally
inject_custom_theme()

# Verify writable data and storage directories
is_writable, failed_path = check_storage_writable()
if not is_writable:
    st.error(
        f"⚠️ Storage Path Error: The path '{failed_path}' is not writable. "
        "Please check filesystem permissions."
    )
    st.stop()

# Ensure existing vector store metadata is aligned with manifest without re-embedding
if not DEMO_MODE:
    store = get_store()
    store.migrate_metadata_from_manifest()

# Role state initialization
if "current_role" not in st.session_state:
    st.session_state.current_role = "Staff"

# Navigation and Pages definition with Material icons
documents_page = st.Page(
    lambda: render_documents_page(role=st.session_state.get("current_role", "Staff")),
    title="Documents",
    icon=":material/description:",
    url_path="documents",
)
chat_page = st.Page(
    lambda: render_chat_page(documents_page=documents_page, role=st.session_state.get("current_role", "Staff")),
    title="Chat",
    icon=":material/chat:",
    url_path="chat",
    default=True,
)
contracts_page = st.Page(
    lambda: render_contracts_page(role=st.session_state.get("current_role", "Staff")),
    title="Contract Analyzer",
    icon=":material/gavel:",
    url_path="contracts",
)
insights_page = st.Page(
    lambda: render_insights_page(role=st.session_state.get("current_role", "Staff")),
    title="Knowledge Insights",
    icon=":material/insights:",
    url_path="insights",
)

# Staff-only pages (Contract Analyzer & Knowledge Insights)
current_role = st.session_state.get("current_role", "Staff")
nav_pages = [chat_page, documents_page]
if current_role == "Staff":
    nav_pages.extend([contracts_page, insights_page])

pg = st.navigation(nav_pages)

# Sidebar header branding, navigation & role selector
with st.sidebar:
    st.markdown(brand_header(), unsafe_allow_html=True)
    if DEMO_MODE:
        st.markdown(
            '<div style="background: rgba(79, 70, 229, 0.12); border: 1px solid rgba(79, 70, 229, 0.3); '
            'border-radius: 8px; padding: 8px 12px; margin-bottom: 12px; font-size: 0.75rem; color: #E0E7FF; line-height: 1.4;">'
            'Public demo - fictional data. Do not upload confidential documents.'
            '</div>',
            unsafe_allow_html=True,
        )
    st.markdown('<div class="sidebar-section-label">WORKSPACE</div>', unsafe_allow_html=True)

    # Viewing As control
    st.markdown('<div class="sidebar-section-label" style="margin-top: 1rem;">VIEWING AS</div>', unsafe_allow_html=True)
    selected_role = st.segmented_control(
        "Viewing as",
        options=["Staff", "Client"],
        default=st.session_state.current_role,
        key="role_switcher",
        label_visibility="collapsed",
    )
    if not selected_role:
        selected_role = st.session_state.current_role

    st.caption("Demo role switch - in production this comes from login (SSO)")

    if selected_role != st.session_state.current_role:
        st.session_state.current_role = selected_role
        clear_chat()
        st.rerun()

# Render active page
pg.run()

# Sidebar footer status block (counts only documents visible to active mode)
current_role = st.session_state.get("current_role", "Staff")
allowed_vis = {"client"} if current_role == "Client" else None
active_store = get_store()
visible_sources = active_store.list_sources(allowed_visibility=allowed_vis)
doc_count = len(visible_sources)
chunk_count = sum(s["chunk_count"] for s in visible_sources)

with st.sidebar:
    st.markdown(sidebar_status_chip(doc_count, chunk_count), unsafe_allow_html=True)
