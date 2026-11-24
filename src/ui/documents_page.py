"""Documents page view for loading sample docs, uploading files, and managing the vector store."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Set
import streamlit as st

from src.chunking import chunk_units
from src.config import (
    ACCESS_MODES,
    DEFAULT_UPLOAD_VISIBILITY,
    DEMO_DAILY_UPLOAD_EMBED_BUDGET,
    DEMO_MAX_CHUNKS_PER_SESSION,
    DEMO_MAX_TOTAL_SESSION_CHUNKS,
    DEMO_MAX_UPLOAD_FILES_PER_SESSION,
    DEMO_MAX_UPLOAD_MB,
    DEMO_MODE,
    MAX_CHUNKS_PER_UPLOAD_BATCH,
    MAX_TOTAL_CHUNKS,
    MAX_UPLOAD_MB,
    PRACTICE_AREAS,
)
from src.demo_limits import check_and_count_upload_embed, get_daily_usage
from src.gemini_client import ErrorCategory, classify_error
from src.loaders import load_directory, load_file
from src.session_store import (
    SessionQuotaExceededError,
    get_global_session_chunks,
    resolve_name_collision,
)
from src.ui.components import (
    demo_callout_card,
    file_type_chip,
    page_header,
    stat_card,
    stat_cards_grid,
)
from src.ui.state import clear_chat, get_store

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_DIR = PROJECT_ROOT / "data" / "sample_docs"


def compute_dir_hashes(directory: Path) -> Dict[str, str]:
    """Compute SHA-256 hashes for all non-hidden document files in a directory."""
    hashes: Dict[str, str] = {}
    if not directory.exists():
        return hashes
    for f in directory.iterdir():
        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in (".pdf", ".docx", ".txt"):
            hashes[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
    return hashes


def render_documents_page(role: str = "Staff") -> None:
    """Render the documents management interface."""
    is_client = role == "Client"

    st.markdown(
        page_header(
            title="Document Management",
            subtitle="Upload, inspect, and index legal documents into DocMind's persistent vector store.",
        ),
        unsafe_allow_html=True,
    )

    store = get_store()
    allowed_vis = {"client"} if is_client else None
    sources = store.list_sources(allowed_visibility=allowed_vis)
    doc_count = len(sources)
    chunk_count = sum(s["chunk_count"] for s in sources)

    # Row of 4 pastel stat cards
    cards = [
        stat_card(label="Indexed Documents", value=str(doc_count), icon="📄", tone="mint"),
        stat_card(label="Total Chunks", value=str(chunk_count), icon="🧩", tone="peach"),
        stat_card(label="Free Quota", value="~1,000 / day", icon="⚡", tone="blue"),
        stat_card(label="Supported Types", value="PDF, DOCX, TXT", icon="📁", tone="pink"),
    ]
    st.markdown(stat_cards_grid(cards), unsafe_allow_html=True)

    if is_client:
        # Client mode: Read-only view
        st.markdown(
            demo_callout_card("Document management is available in Staff mode."),
            unsafe_allow_html=True,
        )

        with st.container(border=True):
            st.subheader("Client-Accessible Documents")
            if not sources:
                st.write("No client-visible documents are currently indexed.")
            else:
                # Read-only table columns: Document Name, Format, Practice Area, Chunks
                h1, h2, h3, h4 = st.columns([5, 2, 3, 2])
                h1.markdown("**Document Name**")
                h2.markdown("**Format**")
                h3.markdown("**Practice Area**")
                h4.markdown("**Chunks**")

                for s in sources:
                    s_name = s["name"]
                    s_chunks = s["chunk_count"]
                    s_type = s.get("file_type") or "DOC"
                    s_pa = s.get("practice_area") or "General"

                    c1, c2, c3, c4 = st.columns([5, 2, 3, 2])
                    c1.write(f"📄 {s_name}")
                    c2.markdown(file_type_chip(s_type), unsafe_allow_html=True)
                    c3.write(s_pa)
                    c4.write(f"{s_chunks} chunks")
        return

    # Staff mode: Full management view
    st.markdown(
        demo_callout_card(
            "Fictional Demo Environment: Sterling & Rauf Law Associates is a fictional law firm. "
            "This system is for demonstration purposes only and does not constitute real legal advice. "
            "Do not upload real confidential or sensitive documents."
        ),
        unsafe_allow_html=True,
    )

    if DEMO_MODE:
        # -------------------------------------------------------------
        # DEMO MODE UI: Read-only Sample Docs + Session-Private Uploads
        # -------------------------------------------------------------
        sample_sources = [s for s in sources if s.get("origin") != "yours"]
        session_sources = [s for s in sources if s.get("origin") == "yours"]
        usage = get_daily_usage()

        # Card 1: Sample Documents (Read-Only)
        with st.container(border=True):
            st.subheader("Sample Law Firm Documents")
            st.caption(
                "Pre-loaded fictional law firm documents covering fee schedules, practice areas, "
                "engagement letters, FAQs, dispute resolution policies, and conflict of interest SOPs. "
                "The sample corpus is read-only in public demo mode."
            )

            if not sample_sources:
                st.write("No sample documents available.")
            else:
                h1, h2, h3, h4, h5 = st.columns([4, 1.5, 2, 2, 2.5])
                h1.markdown("**Document Name**")
                h2.markdown("**Format**")
                h3.markdown("**Practice Area**")
                h4.markdown("**Visibility**")
                h5.markdown("**Status**")

                for s in sample_sources:
                    s_name = s["name"]
                    s_chunks = s["chunk_count"]
                    s_type = s.get("file_type") or "DOC"
                    s_vis = s.get("visibility") or "staff"
                    s_pa = s.get("practice_area") or "General"

                    c1, c2, c3, c4, c5 = st.columns([4, 1.5, 2, 2, 2.5])
                    c1.write(f"📄 {s_name}")
                    c2.markdown(file_type_chip(s_type), unsafe_allow_html=True)
                    c3.write(s_pa)
                    vis_badge = "Staff only" if s_vis == "staff" else "Client"
                    vis_cls = "type-chip-staff" if s_vis == "staff" else "type-chip-client"
                    c4.markdown(f'<span class="{vis_cls}">{vis_badge}</span>', unsafe_allow_html=True)
                    c5.write(f"{s_chunks} chunks &nbsp;•&nbsp; <span style='color: #6B7280; font-size: 0.8rem;'>Sample (Read-only)</span>", unsafe_allow_html=True)

        # Card 2: Your Documents (Session-Private)
        with st.container(border=True):
            st.subheader("Your Documents (Session-Private)")
            st.write(
                "Upload private documents to query alongside the firm knowledge base. "
                "Uploaded documents are stored in memory for this browser session only, isolated from other users, "
                "and automatically cleaned up when the session expires."
            )

            # Quota metrics display
            curr_sess_chunks = sum(s["chunk_count"] for s in session_sources)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Session Files", f"{len(session_sources)} / {DEMO_MAX_UPLOAD_FILES_PER_SESSION}")
            m2.metric("Session Chunks", f"{curr_sess_chunks} / {DEMO_MAX_CHUNKS_PER_SESSION}")
            m3.metric("Max File Size", f"{DEMO_MAX_UPLOAD_MB} MB")
            m4.metric("Daily Upload Embeds", f"{usage['upload_embed_chunks']} / {DEMO_DAILY_UPLOAD_EMBED_BUDGET}")

            st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                upload_vis = st.selectbox(
                    "Document Visibility",
                    options=list(ACCESS_MODES),
                    index=list(ACCESS_MODES).index(DEFAULT_UPLOAD_VISIBILITY),
                    key="demo_upload_vis_select",
                    help="Choose whether uploaded documents are staff-only or accessible to clients.",
                )
            with col_u2:
                upload_pa = st.selectbox(
                    "Practice Area",
                    options=list(PRACTICE_AREAS),
                    index=0,
                    key="demo_upload_pa_select",
                    help="Assign a practice area classification.",
                )

            uploaded_files = st.file_uploader(
                "Choose files to upload (PDF, DOCX, TXT)",
                type=["pdf", "docx", "txt"],
                accept_multiple_files=True,
                key="demo_file_uploader",
            )

            if uploaded_files:
                if len(session_sources) + len(uploaded_files) > DEMO_MAX_UPLOAD_FILES_PER_SESSION:
                    st.error(
                        f"Session limit exceeded: maximum {DEMO_MAX_UPLOAD_FILES_PER_SESSION} files per session "
                        f"(current: {len(session_sources)}, uploading: {len(uploaded_files)})."
                    )
                else:
                    if st.button("Index uploaded documents", type="primary", key="demo_index_btn"):
                        with st.status("Validating and indexing private session documents...", expanded=True) as status_box:
                            max_bytes = DEMO_MAX_UPLOAD_MB * 1024 * 1024
                            parsed_batch = []
                            total_estimated_chunks = 0
                            validation_failed = False

                            existing_source_names = {s["name"] for s in sources}

                            for uf in uploaded_files:
                                orig_name = uf.name
                                file_bytes = uf.getvalue()
                                if len(file_bytes) > max_bytes:
                                    st.write(f"⚠️ `{orig_name}`: Exceeds {DEMO_MAX_UPLOAD_MB} MB limit. Skipped.")
                                    continue

                                try:
                                    resolved_name = resolve_name_collision(orig_name, existing_source_names)
                                    existing_source_names.add(resolved_name)
                                    units = load_file(file_bytes, filename=resolved_name)
                                    if not units:
                                        st.write(f"⚠️ `{orig_name}`: No readable text extracted. Skipped.")
                                        continue
                                    for u in units:
                                        u.source = resolved_name
                                    ch = chunk_units(units)
                                    parsed_batch.append((resolved_name, file_bytes, units, len(ch)))
                                    total_estimated_chunks += len(ch)
                                except Exception as e:
                                    logger.error("Failed parsing '%s': %s", orig_name, type(e).__name__)
                                    st.write(f"❌ `{orig_name}`: Failed to parse file ({type(e).__name__}).")

                            if curr_sess_chunks + total_estimated_chunks > DEMO_MAX_CHUNKS_PER_SESSION:
                                st.error(
                                    f"Upload exceeds session chunk limit of {DEMO_MAX_CHUNKS_PER_SESSION} chunks "
                                    f"(current: {curr_sess_chunks}, new: {total_estimated_chunks})."
                                )
                                validation_failed = True
                            elif get_global_session_chunks() + total_estimated_chunks > DEMO_MAX_TOTAL_SESSION_CHUNKS:
                                st.error(
                                    f"Global demo capacity reached ({DEMO_MAX_TOTAL_SESSION_CHUNKS} total chunks). Please try again later."
                                )
                                validation_failed = True
                            else:
                                budget_ok, budget_msg = check_and_count_upload_embed(total_estimated_chunks)
                                if not budget_ok:
                                    st.error(budget_msg)
                                    validation_failed = True

                            if validation_failed:
                                status_box.update(label="Upload aborted: limits exceeded.", state="error", expanded=True)
                            else:
                                total_chunks_added = 0
                                indexed_count = 0
                                quota_exhausted = False

                                for resolved_name, file_bytes, units, _ in parsed_batch:
                                    try:
                                        f_hash = hashlib.sha256(file_bytes).hexdigest()
                                        rep = store.index_units(
                                            units,
                                            {resolved_name: f_hash},
                                            metadata_by_source={
                                                resolved_name: {
                                                    "visibility": upload_vis,
                                                    "practice_area": upload_pa,
                                                }
                                            },
                                            file_bytes_by_source={resolved_name: len(file_bytes)},
                                        )
                                        added = rep.get("total_chunks_added", 0)
                                        total_chunks_added += added
                                        indexed_count += 1
                                        st.write(f"✅ `{resolved_name}`: Indexed ({added} chunks).")
                                    except Exception as exc:
                                        cat = classify_error(exc)
                                        logger.error("Failed indexing '%s': %s (%s)", resolved_name, type(exc).__name__, cat)
                                        if cat in (ErrorCategory.QUOTA_DAILY, ErrorCategory.RATE_LIMIT_MINUTE):
                                            st.error("Embedding quota reached; remaining files were not indexed.")
                                            quota_exhausted = True
                                            break
                                        else:
                                            st.write(f"❌ `{resolved_name}`: Error indexing ({type(exc).__name__}).")

                                final_state = "error" if quota_exhausted else "complete"
                                status_box.update(
                                    label=f"Completed: Indexed {indexed_count} file(s) ({total_chunks_added} chunks).",
                                    state=final_state,
                                    expanded=False,
                                )
                                st.rerun()

            # Table of session-uploaded documents
            st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
            st.markdown("#### Private Documents in This Session")
            if not session_sources:
                st.info("No private documents uploaded in this session. Documents you upload above will appear here.")
            else:
                h1, h2, h3, h4, h5, h6 = st.columns([4, 1.5, 2, 1.5, 1.5, 1.5])
                h1.markdown("**Document Name**")
                h2.markdown("**Format**")
                h3.markdown("**Practice Area**")
                h4.markdown("**Visibility**")
                h5.markdown("**Chunks**")
                h6.markdown("**Actions**")

                for s in session_sources:
                    s_name = s["name"]
                    s_chunks = s["chunk_count"]
                    s_type = s.get("file_type") or "DOC"
                    s_vis = s.get("visibility") or "staff"
                    s_pa = s.get("practice_area") or "General"

                    c1, c2, c3, c4, c5, c6 = st.columns([4, 1.5, 2, 1.5, 1.5, 1.5])
                    c1.write(f"📄 {s_name}")
                    c2.markdown(file_type_chip(s_type), unsafe_allow_html=True)
                    c3.write(s_pa)
                    vis_badge = "Staff only" if s_vis == "staff" else "Client"
                    vis_cls = "type-chip-staff" if s_vis == "staff" else "type-chip-client"
                    c4.markdown(f'<span class="{vis_cls}">{vis_badge}</span>', unsafe_allow_html=True)
                    c5.write(f"{s_chunks} chunks")

                    with c6:
                        with st.popover("Edit"):
                            st.markdown(f"**Edit `{s_name}`**")
                            cur_vis = s.get("visibility", "staff")
                            cur_pa = s.get("practice_area", "General")
                            vis_idx = list(ACCESS_MODES).index(cur_vis) if cur_vis in ACCESS_MODES else 0
                            pa_idx = list(PRACTICE_AREAS).index(cur_pa) if cur_pa in PRACTICE_AREAS else 0

                            new_vis = st.selectbox(
                                "Visibility",
                                options=list(ACCESS_MODES),
                                index=vis_idx,
                                key=f"demo_edit_vis_{s_name}",
                            )
                            new_pa = st.selectbox(
                                "Practice Area",
                                options=list(PRACTICE_AREAS),
                                index=pa_idx,
                                key=f"demo_edit_pa_{s_name}",
                            )
                            if st.button("Save", key=f"demo_save_meta_{s_name}", type="primary"):
                                store.set_source_metadata(s_name, new_vis, new_pa)
                                st.success("Metadata updated.")
                                st.rerun()

                        if st.button("Delete", key=f"demo_del_{s_name}", type="secondary"):
                            deleted_chunks = store.delete_source(s_name)
                            st.success(f"Deleted '{s_name}' ({deleted_chunks} chunks removed).")
                            st.rerun()
        return

    # -------------------------------------------------------------
    # STANDARD MODE UI: Full corpus management, reload, and delete-all
    # -------------------------------------------------------------
    # Sample Documents Section
    with st.container(border=True):
        st.subheader("Sample Law Firm Documents")
        st.write(
            "Pre-generated fictional law firm documents covering fee schedules, practice areas, "
            "engagement letters, FAQs, dispute resolution policies, and conflict of interest SOPs."
        )

        sample_hashes = compute_dir_hashes(SAMPLE_DIR)
        indexed_source_names = {s["name"] for s in sources}
        all_sample_loaded = bool(sample_hashes) and all(name in indexed_source_names for name in sample_hashes.keys())

        btn_label = "Sample documents already loaded" if all_sample_loaded else "Load sample documents"
        if st.button(btn_label, type="secondary", disabled=all_sample_loaded, key="load_samples_btn"):
            with st.spinner("Loading and indexing sample documents..."):
                try:
                    units, load_report = load_directory(SAMPLE_DIR)
                    manifest_path = SAMPLE_DIR / "manifest.json"
                    metadata_by_source = {}
                    if manifest_path.exists():
                        try:
                            with open(manifest_path, "r", encoding="utf-8") as mf:
                                metadata_by_source = json.load(mf)
                        except Exception:
                            pass

                    rep = store.index_units(units, sample_hashes, metadata_by_source=metadata_by_source)
                    st.success(
                        f"Successfully indexed {len(rep['indexed_files'])} document(s) "
                        f"({rep['total_chunks_added']} chunks added) in {rep['embedding_calls']} embedding call(s)."
                    )
                    if rep["skipped_files"]:
                        st.info(f"Skipped {len(rep['skipped_files'])} unchanged document(s).")
                    st.rerun()
                except Exception as e:
                    logger.error("Failed to index sample documents: %s", type(e).__name__)
                    st.error("Failed to load sample documents. Please try again.")

    # Upload Section (White rounded card)
    with st.container(border=True):
        st.subheader("Upload Documents")
        st.write(
            f"Upload PDF, DOCX, or TXT documents (up to {MAX_UPLOAD_MB} MB each, maximum 10 files, "
            f"limit {MAX_CHUNKS_PER_UPLOAD_BATCH} chunks per batch, {MAX_TOTAL_CHUNKS} total chunks in store)."
        )

        col_u1, col_u2 = st.columns(2)
        with col_u1:
            upload_vis = st.selectbox(
                "Document Visibility",
                options=list(ACCESS_MODES),
                index=list(ACCESS_MODES).index(DEFAULT_UPLOAD_VISIBILITY),
                key="upload_visibility_select",
                help="Choose whether uploaded documents are staff-only or accessible to clients.",
            )
        with col_u2:
            upload_pa = st.selectbox(
                "Practice Area",
                options=list(PRACTICE_AREAS),
                index=0,
                key="upload_practice_area_select",
                help="Assign a practice area classification.",
            )

        uploaded_files = st.file_uploader(
            "Choose files to upload",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=True,
            key="file_uploader",
        )

        if uploaded_files:
            if len(uploaded_files) > 10:
                st.error("Maximum 10 files allowed per upload batch. Please remove some files.")
            else:
                if st.button("Index uploaded documents", type="primary", key="index_uploaded_btn"):
                    with st.status("Validating and indexing uploaded documents...", expanded=True) as status_box:
                        max_bytes = MAX_UPLOAD_MB * 1024 * 1024
                        parsed_batch = []
                        total_estimated_chunks = 0
                        validation_failed = False

                        # Pre-chunk in memory to estimate chunks before any embedding call
                        for uf in uploaded_files:
                            filename = uf.name
                            file_bytes = uf.getvalue()
                            if len(file_bytes) > max_bytes:
                                st.write(f"⚠️ `{filename}`: Exceeds {MAX_UPLOAD_MB} MB size limit. Skipped.")
                                continue

                            try:
                                units = load_file(file_bytes, filename=filename)
                                if not units:
                                    st.write(f"⚠️ `{filename}`: No readable text extracted. Skipped.")
                                    continue
                                chunks = chunk_units(units)
                                parsed_batch.append((filename, file_bytes, units, len(chunks)))
                                total_estimated_chunks += len(chunks)
                            except Exception as e:
                                logger.error("Failed parsing file '%s': %s", filename, type(e).__name__)
                                st.write(f"❌ `{filename}`: Failed to parse file ({type(e).__name__}). Skipped.")

                        if total_estimated_chunks > MAX_CHUNKS_PER_UPLOAD_BATCH:
                            st.error(
                                f"Upload batch exceeds the maximum limit of {MAX_CHUNKS_PER_UPLOAD_BATCH} chunks "
                                f"(estimated: {total_estimated_chunks} chunks). Please upload fewer or smaller documents."
                            )
                            validation_failed = True
                        elif store.count() + total_estimated_chunks > MAX_TOTAL_CHUNKS:
                            st.error(
                                f"Indexing these documents would exceed the maximum database limit of {MAX_TOTAL_CHUNKS} total chunks "
                                f"(current: {store.count()}, estimated new: {total_estimated_chunks}). Please remove documents before uploading."
                            )
                            validation_failed = True

                        if validation_failed:
                            status_box.update(label="Upload aborted: limits exceeded.", state="error", expanded=True)
                        else:
                            total_chunks = 0
                            indexed_count = 0
                            quota_exhausted = False

                            upload_meta = {
                                fn: {"visibility": upload_vis, "practice_area": upload_pa}
                                for fn, _, _, _ in parsed_batch
                            }

                            for filename, file_bytes, units, _ in parsed_batch:
                                try:
                                    f_hash = hashlib.sha256(file_bytes).hexdigest()
                                    rep = store.index_units(
                                        units,
                                        {filename: f_hash},
                                        metadata_by_source=upload_meta,
                                    )

                                    if rep["indexed_files"]:
                                        chunks_added = rep["total_chunks_added"]
                                        total_chunks += chunks_added
                                        indexed_count += 1
                                        st.write(f"✅ `{filename}`: Indexed successfully ({chunks_added} chunks).")
                                    elif rep["skipped_files"]:
                                        st.write(f"ℹ️ `{filename}`: Already indexed (unchanged).")

                                except Exception as exc:
                                    cat = classify_error(exc)
                                    logger.error("Failed indexing file '%s': %s (%s)", filename, type(exc).__name__, cat)
                                    if cat in (ErrorCategory.QUOTA_DAILY, ErrorCategory.RATE_LIMIT_MINUTE):
                                        st.error("Embedding quota reached; the remaining files were not indexed.")
                                        quota_exhausted = True
                                        break
                                    else:
                                        st.write(f"❌ `{filename}`: Failed to process ({type(exc).__name__}). Skipped.")

                            final_state = "error" if quota_exhausted else "complete"
                            status_box.update(
                                label=f"Completed: Indexed {indexed_count} file(s) ({total_chunks} chunks).",
                                state=final_state,
                                expanded=False,
                            )
                            st.rerun()

    # Indexed Documents Section (White rounded card with table list)
    with st.container(border=True):
        st.subheader("Indexed Documents")
        if not sources:
            st.write("No documents are currently indexed.")
        else:
            # Table Header
            h1, h2, h3, h4, h5, h6 = st.columns([4, 1.5, 2, 1.5, 1.5, 1.5])
            h1.markdown("**Document Name**")
            h2.markdown("**Format**")
            h3.markdown("**Practice Area**")
            h4.markdown("**Visibility**")
            h5.markdown("**Chunks**")
            h6.markdown("**Actions**")

            for s in sources:
                s_name = s["name"]
                s_chunks = s["chunk_count"]
                s_type = s.get("file_type") or "DOC"
                s_vis = s.get("visibility") or "staff"
                s_pa = s.get("practice_area") or "General"

                c1, c2, c3, c4, c5, c6 = st.columns([4, 1.5, 2, 1.5, 1.5, 1.5])
                c1.write(f"📄 {s_name}")
                c2.markdown(file_type_chip(s_type), unsafe_allow_html=True)
                c3.write(s_pa)
                vis_badge = "Staff only" if s_vis == "staff" else "Client"
                vis_cls = "type-chip-staff" if s_vis == "staff" else "type-chip-client"
                c4.markdown(f'<span class="{vis_cls}">{vis_badge}</span>', unsafe_allow_html=True)
                c5.write(f"{s_chunks} chunks")

                with c6:
                    with st.popover("Edit"):
                        st.markdown(f"**Edit `{s_name}`**")
                        cur_vis = s.get("visibility", "staff")
                        cur_pa = s.get("practice_area", "General")
                        vis_idx = list(ACCESS_MODES).index(cur_vis) if cur_vis in ACCESS_MODES else 0
                        pa_idx = list(PRACTICE_AREAS).index(cur_pa) if cur_pa in PRACTICE_AREAS else 0

                        new_vis = st.selectbox(
                            "Visibility",
                            options=list(ACCESS_MODES),
                            index=vis_idx,
                            key=f"edit_vis_{s_name}",
                        )
                        new_pa = st.selectbox(
                            "Practice Area",
                            options=list(PRACTICE_AREAS),
                            index=pa_idx,
                            key=f"edit_pa_{s_name}",
                        )
                        if st.button("Save", key=f"save_meta_{s_name}", type="primary"):
                            store.set_source_metadata(s_name, new_vis, new_pa)
                            st.success("Metadata updated.")
                            st.rerun()

                    if st.button("Delete", key=f"del_{s_name}", type="secondary"):
                        deleted_chunks = store.delete_source(s_name)
                        st.success(f"Deleted '{s_name}' ({deleted_chunks} chunks removed).")
                        st.rerun()

    # Danger Zone: Delete All
    st.markdown("---")
    st.subheader("Danger Zone")
    with st.expander("Delete all documents"):
        st.warning("This will permanently remove all indexed documents and chunks from the vector database.")
        confirm = st.checkbox("I understand and confirm that I want to delete all indexed documents.", key="confirm_del_all")
        if st.button("Delete All Documents", type="primary", disabled=not confirm, key="btn_del_all"):
            store.reset()
            clear_chat()
            st.success("All indexed documents have been deleted.")
            st.rerun()


if __name__ == "__main__":
    render_documents_page()
