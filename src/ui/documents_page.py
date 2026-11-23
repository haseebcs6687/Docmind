"""Documents page view for loading sample docs, uploading files, and managing the vector store."""

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict
import streamlit as st

from src.config import MAX_UPLOAD_MB
from src.loaders import load_directory, load_file
from src.ui.state import clear_chat, get_store

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_DIR = PROJECT_ROOT / "data" / "sample_docs"


def compute_dir_hashes(directory: Path) -> Dict[str, str]:
    """Compute SHA-256 hashes for all non-hidden files in a directory."""
    hashes: Dict[str, str] = {}
    if not directory.exists():
        return hashes
    for f in directory.iterdir():
        if f.is_file() and not f.name.startswith("."):
            hashes[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
    return hashes


def render_documents_page() -> None:
    """Render the documents management interface."""
    st.title("Document Management")
    st.caption("Upload, inspect, and index legal documents into DocMind's persistent vector store.")

    store = get_store()
    sources = store.list_sources()
    doc_count = len(sources)
    chunk_count = store.count()

    # Metrics row
    col_m1, col_m2 = st.columns(2)
    col_m1.metric("Indexed Documents", doc_count)
    col_m2.metric("Total Chunks", chunk_count)

    # Disclaimers
    st.info(
        "ℹ️ **Fictional Demo Environment**: Sterling & Rauf Law Associates is a fictional law firm. "
        "This system is for demonstration purposes only and does not constitute real legal advice. "
        "Do not upload real confidential or sensitive documents."
    )
    st.caption(
        "⚡ Powered by Gemini API free tier (~1,000 embedding requests/day). "
        "Documents are chunked and embedded in batches of up to 20 to conserve quota."
    )

    st.markdown("---")

    # Sample Documents Section
    st.subheader("Sample Law Firm Documents")
    st.write(
        "Pre-generated fictional law firm documents covering fee schedules, practice areas, "
        "engagement letters, FAQs, dispute resolution policies, and conflict of interest SOPs."
    )

    sample_hashes = compute_dir_hashes(SAMPLE_DIR)
    indexed_source_names = {s["name"] for s in sources}
    all_sample_loaded = bool(sample_hashes) and all(name in indexed_source_names for name in sample_hashes.keys())

    btn_label = "Sample documents already loaded" if all_sample_loaded else "Load sample documents"
    if st.button(btn_label, type="primary", disabled=all_sample_loaded, key="load_samples_btn"):
        with st.spinner("Loading and indexing sample documents..."):
            try:
                units, load_report = load_directory(SAMPLE_DIR)
                rep = store.index_units(units, sample_hashes)
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

    st.markdown("---")

    # Upload Section
    st.subheader("Upload Documents")
    st.write(f"Upload PDF, DOCX, or TXT documents (up to {MAX_UPLOAD_MB} MB each, maximum 10 files per batch).")

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
                with st.status("Indexing uploaded documents...", expanded=True) as status_box:
                    total_chunks = 0
                    indexed_count = 0
                    max_bytes = MAX_UPLOAD_MB * 1024 * 1024

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

                            f_hash = hashlib.sha256(file_bytes).hexdigest()
                            rep = store.index_units(units, {filename: f_hash})

                            if rep["indexed_files"]:
                                chunks_added = rep["total_chunks_added"]
                                total_chunks += chunks_added
                                indexed_count += 1
                                st.write(f"✅ `{filename}`: Indexed successfully ({chunks_added} chunks).")
                            elif rep["skipped_files"]:
                                st.write(f"ℹ️ `{filename}`: Already indexed (unchanged).")

                        except Exception as exc:
                            logger.error("Failed indexing file '%s': %s", filename, type(exc).__name__)
                            st.write(f"❌ `{filename}`: Failed to process ({type(exc).__name__}). Skipped.")

                    status_box.update(
                        label=f"Completed: Indexed {indexed_count} file(s) ({total_chunks} chunks).",
                        state="complete",
                        expanded=False,
                    )
                    st.rerun()

    st.markdown("---")

    # Indexed Documents Table
    st.subheader("Indexed Documents")
    if not sources:
        st.write("No documents are currently indexed.")
    else:
        # Table Header
        h1, h2, h3, h4 = st.columns([5, 2, 2, 2])
        h1.markdown("**Document Name**")
        h2.markdown("**Format**")
        h3.markdown("**Chunks**")
        h4.markdown("**Action**")

        for s in sources:
            s_name = s["name"]
            s_chunks = s["chunk_count"]
            s_type = (s.get("file_type") or "DOC").upper()

            c1, c2, c3, c4 = st.columns([5, 2, 2, 2])
            c1.write(f"📄 {s_name}")
            c2.write(f"`{s_type}`")
            c3.write(f"{s_chunks} chunks")
            if c4.button("Delete", key=f"del_{s_name}", type="secondary"):
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
