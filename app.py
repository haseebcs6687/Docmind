"""DocMind - Streamlit Knowledge Agent Entrypoint."""

import sys
from pathlib import Path
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.logging_setup import configure_logging
from src.ui.chat_page import render_chat_page
from src.ui.documents_page import render_documents_page
from src.ui.state import get_store

# Configure server-side logging
configure_logging()

# Streamlit Page Configuration
st.set_page_config(
    page_title="DocMind",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Navigation and Pages definition
documents_page = st.Page(render_documents_page, title="Documents", icon="📁", url_path="documents")
chat_page = st.Page(
    lambda: render_chat_page(documents_page=documents_page),
    title="Chat",
    icon="💬",
    url_path="chat",
    default=True,
)

pg = st.navigation([chat_page, documents_page])

# Sidebar header branding
with st.sidebar:
    st.title("⚖️ DocMind")
    st.caption("Chat with your documents")
    st.markdown("---")

# Render active page
pg.run()

# Sidebar footer status
store = get_store()
doc_count = len(store.list_sources())
chunk_count = store.count()

with st.sidebar:
    st.markdown("---")
    st.caption(f"📊 {doc_count} documents | {chunk_count} chunks")
