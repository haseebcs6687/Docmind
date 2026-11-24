"""Session state and cached resource helpers for DocMind Streamlit UI."""

import logging
import uuid
from typing import Any, Dict, List, Optional, Union
import streamlit as st

from src.analytics import AnalyticsStore
from src.config import (
    DEMO_MODE,
    MAX_QUESTIONS_PER_SESSION,
    MIN_SECONDS_BETWEEN_QUESTIONS,
)
from src.rag import ChatSession
from src.session_store import CompositeStore, SessionDocStore, get_session_store
from src.shared_index import ensure_shared_index
from src.vectorstore import VectorStore

logger = logging.getLogger(__name__)


@st.cache_resource
def get_shared_store() -> VectorStore:
    """Return a cached ChromaDB VectorStore instance shared across all sessions."""
    store = VectorStore(read_only=DEMO_MODE)
    if DEMO_MODE:
        ensure_shared_index(store)
    return store


def get_browser_session_id() -> str:
    """Return or initialize an isolated UUID for the current browser session."""
    if "browser_session_id" not in st.session_state:
        st.session_state.browser_session_id = str(uuid.uuid4())
    return st.session_state.browser_session_id


def get_current_session_store() -> Optional[SessionDocStore]:
    """Return the SessionDocStore for the current browser session in demo mode."""
    if not DEMO_MODE:
        return None
    sess_id = get_browser_session_id()
    return get_session_store(sess_id)


def get_store() -> Union[VectorStore, CompositeStore]:
    """Return the active store facade for the current session."""
    shared = get_shared_store()
    if not DEMO_MODE:
        return shared
    sess_id = get_browser_session_id()
    sess_store = get_session_store(sess_id)
    return CompositeStore(shared=shared, session=sess_store)


@st.cache_resource
def get_analytics() -> AnalyticsStore:
    """Return a cached AnalyticsStore instance shared across all sessions."""
    store = AnalyticsStore()
    if DEMO_MODE:
        from src.analytics import ensure_demo_activity
        ensure_demo_activity(store)
    return store


def get_session(access_mode: str = "staff") -> ChatSession:
    """Return or initialize the per-session ChatSession for the specified access mode."""
    session_key = f"chat_session_{access_mode}"
    if session_key not in st.session_state:
        store = get_store()
        analytics = get_analytics()
        sess_id = get_browser_session_id()
        st.session_state[session_key] = ChatSession(
            store=store,
            cooldown_seconds=MIN_SECONDS_BETWEEN_QUESTIONS,
            max_questions=MAX_QUESTIONS_PER_SESSION,
            access_mode=access_mode,
            analytics=analytics,
            session_id=sess_id,
        )
    return st.session_state[session_key]


def init_messages() -> List[Dict[str, Any]]:
    """Initialize and return the message history list in st.session_state."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    return st.session_state.messages


def clear_chat() -> None:
    """Clear conversation history and reset ChatSession across modes."""
    for key in list(st.session_state.keys()):
        if key.startswith("chat_session_"):
            st.session_state[key].reset()
    if "chat_session" in st.session_state:
        st.session_state.chat_session.reset()
    st.session_state.messages = []
