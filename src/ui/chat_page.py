"""Chat page view for querying legal documents with citations."""

import logging
from typing import Any, Optional
import streamlit as st

from src.config import get_gemini_api_key
from src.gemini_client import GeminiServiceError
from src.rag import GenerationError
from src.ui.components import not_found_card, page_header, source_mini_card
from src.ui.state import clear_chat, get_session, get_store, init_messages
from src.vectorstore import EmbeddingError

logger = logging.getLogger(__name__)

STARTER_QUESTIONS = [
    "What is the initial consultation fee?",
    "What happens if an invoice is paid late?",
    "How long are client files kept?",
    "How long does the conflict check take?",
]


def render_chat_page(documents_page: Optional[Any] = None) -> None:
    """Render the primary DocMind chat interface."""
    # Startup check: verify Gemini API key is configured
    try:
        get_gemini_api_key()
    except ValueError:
        st.markdown(
            page_header(
                title="Ask your documents",
                subtitle="Answers are grounded in the uploaded files and always cite their source.",
            ),
            unsafe_allow_html=True,
        )
        st.warning(
            "**Gemini API Key Required**\n\n"
            "DocMind requires a Google Gemini API key to generate answers and embeddings. "
            "Please configure `GEMINI_API_KEY` in your environment or `.env` file to begin."
        )
        return

    store = get_store()
    chunk_count = store.count()

    # Empty store state
    if chunk_count == 0:
        st.markdown(
            page_header(
                title="Ask your documents",
                subtitle="Answers are grounded in the uploaded files and always cite their source.",
            ),
            unsafe_allow_html=True,
        )
        st.info("No documents are currently indexed in DocMind.")
        st.markdown(
            "To begin asking questions with legal citations, head over to the "
            "**Documents** page to load sample documents or upload your own files."
        )
        if documents_page is not None:
            st.page_link(documents_page, label="Go to Documents Page", icon=":material/description:")
        return

    # Populated store state: Page header with Clear Conversation ghost button
    col_title, col_action = st.columns([5, 1])
    with col_title:
        st.markdown(
            page_header(
                title="Ask your documents",
                subtitle="Answers are grounded in the uploaded files and always cite their source.",
            ),
            unsafe_allow_html=True,
        )
    with col_action:
        if st.button("Clear conversation", key="clear_chat_btn", use_container_width=True):
            clear_chat()
            st.rerun()

    messages = init_messages()

    # Render starter buttons when there is no conversation history
    clicked_prompt: Optional[str] = None
    if not messages:
        st.markdown("##### Suggested questions")
        cols = st.columns(2)
        for i, prompt_text in enumerate(STARTER_QUESTIONS):
            with cols[i % 2]:
                if st.button(prompt_text, key=f"starter_btn_{i}", use_container_width=True):
                    clicked_prompt = prompt_text

    # Render conversation history
    for msg in messages:
        role = msg.get("role", "assistant")
        with st.chat_message(role):
            if role == "user":
                st.markdown(msg.get("content", ""))
            else:
                found = msg.get("found", True)
                content = msg.get("content", "")
                if not found:
                    st.markdown(not_found_card(content), unsafe_allow_html=True)
                else:
                    st.markdown(content)
                    sources = msg.get("sources", [])
                    if sources:
                        with st.expander(f"Sources ({len(sources)})", expanded=False):
                            for s in sources:
                                citation_str = s.get("label") or s.get("citation") or s.get("source", "Document")
                                score_val = s.get("score", 0.0)
                                snippet_str = s.get("snippet", "").strip()
                                st.markdown(
                                    source_mini_card(
                                        citation=citation_str,
                                        score=score_val,
                                        snippet=snippet_str,
                                    ),
                                    unsafe_allow_html=True,
                                )

                latency = msg.get("latency_seconds")
                if latency is not None:
                    cached_tag = ' • <span style="color:#059669; font-weight:600;">cached</span>' if msg.get("cached") else ""
                    st.markdown(
                        f'<div class="latency-caption">⏱️ Response time: {latency:.2f}s{cached_tag}</div>',
                        unsafe_allow_html=True,
                    )

    # Friendly error callout with "Try again" button if a previous request failed
    if st.session_state.get("last_error"):
        st.error(st.session_state["last_error"])
        if st.session_state.get("last_failed_query"):
            if st.button("Try again", key="try_again_btn"):
                clicked_prompt = st.session_state["last_failed_query"]
                st.session_state["last_error"] = None
                st.session_state["last_failed_query"] = None
                st.rerun()

    # Chat input widget (max 500 characters)
    user_input = st.chat_input("Ask a question about your documents...", max_chars=500)
    active_query = clicked_prompt or user_input

    if active_query:
        if len(active_query) > 500:
            st.warning("Your question exceeds the maximum limit of 500 characters. Please shorten it.")
            return

        session = get_session()
        try:
            with st.spinner("Searching your documents..."):
                response = session.ask(active_query)

            # Clear any previous error on success
            st.session_state["last_error"] = None
            st.session_state["last_failed_query"] = None

            formatted_sources = []
            for s in response.sources:
                if isinstance(s, dict):
                    label = s.get("citation") or s.get("source", "Document")
                    formatted_sources.append({
                        "source": s.get("source", ""),
                        "page": s.get("page"),
                        "section": s.get("section"),
                        "label": label,
                        "score": s.get("score", 0.0),
                        "snippet": s.get("snippet", ""),
                    })
                else:
                    label = getattr(s, "citation_label", lambda: str(s))()
                    formatted_sources.append({
                        "source": getattr(s, "source", ""),
                        "page": getattr(s, "page", None),
                        "section": getattr(s, "section", None),
                        "label": label,
                        "score": getattr(s, "score", 0.0),
                        "snippet": getattr(s, "snippet", ""),
                    })

            latency_sec = getattr(response, "latency_ms", 0.0) / 1000.0

            st.session_state.messages.append({"role": "user", "content": active_query})
            st.session_state.messages.append({
                "role": "assistant",
                "content": response.answer,
                "found": response.found,
                "sources": formatted_sources,
                "latency_seconds": latency_sec,
                "cached": getattr(response, "cached", False),
                "model_used": getattr(response, "model_used", ""),
                "fallback_used": getattr(response, "fallback_used", False),
            })
            st.rerun()

        except GeminiServiceError as e:
            logger.error("GeminiServiceError in chat UI: %s", getattr(e, "category", type(e).__name__))
            st.session_state["last_error"] = e.user_message
            st.session_state["last_failed_query"] = active_query
            st.rerun()
        except (EmbeddingError, GenerationError) as e:
            logger.error("RAG error in chat UI: %s", type(e).__name__)
            user_msg = getattr(e, "user_message", None) or "An error occurred while processing your question. Please try again."
            st.session_state["last_error"] = user_msg
            st.session_state["last_failed_query"] = active_query
            st.rerun()
        except Exception as e:
            logger.error("Unexpected error in chat UI: %s", type(e).__name__)
            user_msg = getattr(e, "user_message", None) or "An unexpected error occurred while processing your question. Please try again."
            st.session_state["last_error"] = user_msg
            st.session_state["last_failed_query"] = active_query
            st.rerun()


if __name__ == "__main__":
    render_chat_page()
