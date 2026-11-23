"""DocMind - Streamlit Knowledge Agent Entrypoint."""

import sys
from pathlib import Path
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.logging_setup import configure_logging
from src.ui.chat_page import render_chat_page
from src.ui.components import brand_header, sidebar_status_chip
from src.ui.documents_page import render_documents_page
from src.ui.state import get_store
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

# Navigation and Pages definition with Material icons
documents_page = st.Page(
    render_documents_page,
    title="Documents",
    icon=":material/description:",
    url_path="documents",
)
chat_page = st.Page(
    lambda: render_chat_page(documents_page=documents_page),
    title="Chat",
    icon=":material/chat:",
    url_path="chat",
    default=True,
)

pg = st.navigation([chat_page, documents_page])

# Sidebar header branding & section label
with st.sidebar:
    st.markdown(brand_header(), unsafe_allow_html=True)
    st.markdown('<div class="sidebar-section-label">WORKSPACE</div>', unsafe_allow_html=True)

# Render active page
pg.run()

# Sidebar footer status block
store = get_store()
doc_count = len(store.list_sources())
chunk_count = store.count()

with st.sidebar:
    st.markdown(sidebar_status_chip(doc_count, chunk_count), unsafe_allow_html=True)
