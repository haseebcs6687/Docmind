"""Chat page view for querying legal documents with citations."""

import html
import logging
from typing import Any, Dict, List, Optional
import streamlit as st

from src.config import PRACTICE_AREAS, get_gemini_api_key
from src.drafting import (
    DraftAccessError,
    DraftCooldownError,
    DraftResult,
    DraftSessionLimitError,
    DraftValidationError,
    draft_client_reply,
)
from src.gemini_client import GeminiServiceError
from src.memo import build_memo_docx, memo_filename
from src.rag import GenerationError, check_small_talk
from src.ui.components import not_found_card, page_header, role_chip, source_mini_card
from src.ui.state import clear_chat, get_session, get_store, init_messages
from src.vectorstore import EmbeddingError

logger = logging.getLogger(__name__)

STAFF_STARTER_QUESTIONS = [
    "What steps do staff follow during client intake?",
    "How long does the conflict check take?",
    "How quickly must a data breach be reported internally?",
    "Who do I escalate a client dispute to?",
]

CLIENT_STARTER_QUESTIONS = [
    "What is the initial consultation fee?",
    "What happens if an invoice is paid late?",
    "How long are client files kept?",
    "What are your office hours?",
]


@st.dialog("Draft Client Reply", width="large")
def draft_dialog(
    msg_idx: int, question: str, answer: str, sources: List[Dict[str, Any]]
) -> None:
    """Dialog for drafting a grounded client reply from verified sources."""
    st.markdown(
        f'<div style="font-size:0.9rem; color:#475569; margin-bottom:1rem;">'
        f"Draft a grounded client reply from verified sources for: <b>{html.escape(question)}</b>"
        f"</div>",
        unsafe_allow_html=True,
    )
    tone = st.radio(
        "Tone",
        options=["Formal", "Friendly"],
        horizontal=True,
        key=f"dialog_tone_{msg_idx}",
    )
    col_c, col_s = st.columns(2)
    with col_c:
        client_name = st.text_input(
            "Client name",
            value="",
            placeholder="[Client Name]",
            key=f"dialog_client_{msg_idx}",
        )
    with col_s:
        sender_name = st.text_input(
            "Your name",
            value="",
            placeholder="[Your Name]",
            key=f"dialog_sender_{msg_idx}",
        )
    include_sources = st.checkbox(
        "Mention source documents",
        value=True,
        key=f"dialog_inc_src_{msg_idx}",
    )

    if st.button(
        "Generate draft",
        type="primary",
        key=f"dialog_gen_btn_{msg_idx}",
        use_container_width=True,
    ):
        with st.spinner("Drafting..."):
            try:
                res = draft_client_reply(
                    question=question,
                    answer=answer,
                    sources=sources,
                    tone=tone,
                    client_name=client_name or "[Client Name]",
                    sender_name=sender_name or "[Your Name]",
                    include_sources=include_sources,
                    access_mode="staff",
                )
                st.session_state[f"active_draft_{msg_idx}"] = res
                st.session_state[f"draft_error_{msg_idx}"] = None
            except (
                DraftAccessError,
                DraftValidationError,
                DraftSessionLimitError,
                DraftCooldownError,
            ) as e:
                st.session_state[f"draft_error_{msg_idx}"] = str(e)
            except Exception as e:
                st.session_state[f"draft_error_{msg_idx}"] = f"Drafting error: {e}"

    if st.session_state.get(f"draft_error_{msg_idx}"):
        st.error(st.session_state[f"draft_error_{msg_idx}"])

    draft_result: Optional[DraftResult] = st.session_state.get(
        f"active_draft_{msg_idx}"
    )
    if draft_result:
        st.markdown("---")
        subj = st.text_input(
            "Subject",
            value=draft_result.subject,
            key=f"dialog_subj_val_{msg_idx}",
        )
        body = st.text_area(
            "Body",
            value=draft_result.body,
            height=200,
            key=f"dialog_body_val_{msg_idx}",
        )
        st.caption("Draft generated from the cited sources only. Review before sending.")

        if draft_result.unverified_figures:
            figs_str = html.escape(", ".join(draft_result.unverified_figures))
            st.markdown(
                f'<div style="background-color:#FEF3C7; border:1px solid #F59E0B; border-radius:8px; padding:0.75rem; margin:0.75rem 0; font-size:0.875rem; color:#92400E;">'
                f"⚠️ <b>Warning:</b> These figures were not found in the cited sources: <b>{figs_str}</b>. Please check before sending."
                f"</div>",
                unsafe_allow_html=True,
            )

        txt_data = f"Subject: {subj}\n\n{body}"
        st.download_button(
            "Download text (.txt)",
            data=txt_data,
            file_name=f"client-reply-{msg_idx}.txt",
            mime="text/plain",
            key=f"dialog_dl_btn_{msg_idx}",
            use_container_width=True,
        )
        cached_label = " • cached" if draft_result.cached else ""
        st.markdown(
            f'<div style="font-size:0.8rem; color:#64748B; margin-top:0.5rem;">'
            f"Model: {html.escape(draft_result.model_used)} • Latency: {draft_result.latency_ms:.1f}ms{cached_label}"
            f"</div>",
            unsafe_allow_html=True,
        )


def render_chat_page(documents_page: Optional[Any] = None, role: str = "Staff") -> None:
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

    access_mode = "client" if role == "Client" else "staff"
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
        st.markdown(f'<div style="margin-top: -0.5rem; margin-bottom: 0.75rem;">{role_chip(role)}</div>', unsafe_allow_html=True)
        st.info("No documents are currently indexed in DocMind.")
        st.markdown(
            "To begin asking questions with legal citations, head over to the "
            "**Documents** page to load sample documents or upload your own files."
        )
        if documents_page is not None:
            st.page_link(documents_page, label="Go to Documents Page", icon=":material/description:")
        return

    # Initialize messages list early for header buttons
    messages = init_messages()

    # Populated store state: Page header with role chip, Export Memo, & Clear Conversation
    col_title, col_memo, col_action = st.columns([4, 1.5, 1.5])
    with col_title:
        st.markdown(
            page_header(
                title="Ask your documents",
                subtitle="Answers are grounded in the uploaded files and always cite their source.",
            ),
            unsafe_allow_html=True,
        )
        st.markdown(f'<div style="margin-top: -0.5rem; margin-bottom: 0.75rem;">{role_chip(role)}</div>', unsafe_allow_html=True)
    with col_memo:
        # Memo Export Button (enabled only when at least one answered turn exists)
        answered_turns = [
            m for m in messages
            if m.get("role") == "assistant"
            and m.get("found") is True
            and m.get("sources")
            and check_small_talk(m.get("question") or "") is None
        ]
        if answered_turns:
            try:
                memo_bytes = build_memo_docx(messages, access_mode)
                st.download_button(
                    label="Export memo",
                    data=memo_bytes,
                    file_name=memo_filename(),
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key="export_memo_btn",
                    use_container_width=True,
                    icon=":material/description:",
                )
            except Exception:
                st.button(
                    "Export memo",
                    disabled=True,
                    key="export_memo_err_btn",
                    use_container_width=True,
                    icon=":material/description:",
                )
        else:
            st.button(
                "Export memo",
                disabled=True,
                key="export_memo_disabled_btn",
                help="Ask at least one question to export a research memo.",
                use_container_width=True,
                icon=":material/description:",
            )
    with col_action:
        if st.button("Clear conversation", key="clear_chat_btn", use_container_width=True):
            clear_chat()
            st.rerun()

    # Filters expander for practice area filtering
    with st.expander("Filters", expanded=False):
        selected_pas = st.multiselect(
            "Filter by practice area",
            options=list(PRACTICE_AREAS),
            default=[],
            key=f"pa_filter_{access_mode}",
            help="Optional: restrict retrieval to documents in specific practice areas",
        )

    # Render starter buttons when there is no conversation history
    clicked_prompt: Optional[str] = None
    if not messages:
        st.markdown("##### Suggested questions")
        starters = CLIENT_STARTER_QUESTIONS if access_mode == "client" else STAFF_STARTER_QUESTIONS
        cols = st.columns(2)
        for i, prompt_text in enumerate(starters):
            with cols[i % 2]:
                if st.button(prompt_text, key=f"starter_btn_{access_mode}_{i}", use_container_width=True):
                    clicked_prompt = prompt_text

    # Render conversation history
    for idx, msg in enumerate(messages):
        msg_role = msg.get("role", "assistant")
        with st.chat_message(msg_role):
            if msg_role == "user":
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
                                vis_val = s.get("visibility")
                                pa_val = s.get("practice_area")
                                st.markdown(
                                    source_mini_card(
                                        citation=citation_str,
                                        score=score_val,
                                        snippet=snippet_str,
                                        visibility=vis_val,
                                        practice_area=pa_val,
                                    ),
                                    unsafe_allow_html=True,
                                )

                    # In Staff mode, render ghost button "Draft client reply" if found=True and sources exist
                    if access_mode == "staff" and sources:
                        msg_q = msg.get("question") or (
                            messages[idx - 1].get("content")
                            if idx > 0 and messages[idx - 1].get("role") == "user"
                            else "Client Question"
                        )
                        if st.button(
                            "Draft client reply",
                            key=f"draft_reply_btn_{idx}",
                            help="Draft a professional client email from the verified sources",
                            icon=":material/mail:",
                        ):
                            draft_dialog(idx, msg_q, content, sources)

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

        session = get_session(access_mode=access_mode)
        try:
            with st.spinner("Searching your documents..."):
                response = session.ask(active_query, practice_areas=selected_pas if selected_pas else None)

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
                        "text": s.get("text", "") or s.get("snippet", ""),
                        "visibility": s.get("visibility"),
                        "practice_area": s.get("practice_area"),
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
                        "text": getattr(s, "text", "") or getattr(s, "snippet", ""),
                        "visibility": getattr(s, "visibility", None),
                        "practice_area": getattr(s, "practice_area", None),
                    })

            latency_sec = getattr(response, "latency_ms", 0.0) / 1000.0

            st.session_state.messages.append({"role": "user", "content": active_query})
            st.session_state.messages.append({
                "role": "assistant",
                "question": active_query,
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
