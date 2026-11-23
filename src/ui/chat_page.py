"""Chat page view for querying legal documents with citations."""

import logging
from typing import Any, Optional
import streamlit as st

from src.rag import GenerationError
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
    store = get_store()
    chunk_count = store.count()

    # Empty store state
    if chunk_count == 0:
        st.title("DocMind Chat")
        st.info("No documents are currently indexed in DocMind.")
        st.markdown(
            "To begin asking questions with legal citations, head over to the "
            "**Documents** page to load sample documents or upload your own files."
        )
        if documents_page is not None:
            st.page_link(documents_page, label="Go to Documents Page", icon="📁")
        return

    # Populated store state
    col_title, col_action = st.columns([5, 1])
    with col_title:
        st.title("DocMind Chat")
        st.caption("Ask questions cited directly from your indexed legal documents.")
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
                    st.warning(content)
                else:
                    st.markdown(content)
                    sources = msg.get("sources", [])
                    if sources:
                        with st.expander(f"Sources ({len(sources)})", expanded=False):
                            for s in sources:
                                score_pct = int(s.get("score", 0.0) * 100)
                                label = s.get("label") or s.get("source", "Document")
                                st.markdown(f"**{label}** &nbsp; `Relevance: {score_pct}%`")
                                snippet = s.get("snippet", "").strip()
                                if snippet:
                                    st.markdown(f"> {snippet}")
                                st.divider()

                latency = msg.get("latency_seconds")
                if latency is not None:
                    st.caption(f"⏱️ Response time: {latency:.2f}s")

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
            })
            st.rerun()

        except EmbeddingError as e:
            logger.error("EmbeddingError in chat UI: %s", type(e).__name__)
            st.error(
                "An error occurred while generating embeddings. "
                "If this is a rate limit, please wait a minute and try again."
            )
        except GenerationError as e:
            logger.error("GenerationError in chat UI: %s", type(e).__name__)
            st.error("An error occurred while generating the answer. Please try again.")
        except Exception as e:
            logger.error("Unexpected error in chat UI: %s", type(e).__name__)
            st.error("An unexpected error occurred while processing your question. Please try again.")


if __name__ == "__main__":
    render_chat_page()
