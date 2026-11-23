"""Session state and cached resource helpers for DocMind Streamlit UI."""

import logging
from typing import Any, Dict, List
import streamlit as st

from src.config import MAX_QUESTIONS_PER_SESSION, MIN_SECONDS_BETWEEN_QUESTIONS
from src.rag import ChatSession
from src.vectorstore import VectorStore

logger = logging.getLogger(__name__)


@st.cache_resource
def get_store() -> VectorStore:
    """Return a cached ChromaDB VectorStore instance shared across all sessions."""
    return VectorStore()


def get_session() -> ChatSession:
    """Return or initialize the per-session ChatSession."""
    if "chat_session" not in st.session_state:
        store = get_store()
        st.session_state.chat_session = ChatSession(
            store=store,
            cooldown_seconds=MIN_SECONDS_BETWEEN_QUESTIONS,
            max_questions=MAX_QUESTIONS_PER_SESSION,
        )
    return st.session_state.chat_session


def init_messages() -> List[Dict[str, Any]]:
    """Initialize and return the message history list in st.session_state."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    return st.session_state.messages


def clear_chat() -> None:
    """Clear conversation history and reset ChatSession."""
    if "chat_session" in st.session_state:
        st.session_state.chat_session.reset()
    st.session_state.messages = []
