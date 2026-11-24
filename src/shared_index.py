"""Shared demo index loader and synchronization for zero-API startup."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from src.config import GEMINI_EMBED_MODEL
from src.loaders import load_file
from src.vectorstore import VectorStore

logger = logging.getLogger(__name__)

DEFAULT_EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "demo_index"


def compute_file_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def ensure_shared_index(
    store: VectorStore,
    demo_index_dir: Optional[Path] = None,
    rebuild_fn: Optional[Callable[[], None]] = None,
) -> bool:
    """Ensure the vector store contains the shared sample corpus.

    - If the store is empty or its fingerprint differs from the export:
      Attempts to import from data/demo_index (index.json + vectors.npz) with ZERO API calls.
    - If export is missing or its recorded embedding model differs from GEMINI_EMBED_MODEL:
      Falls back to rebuilding from data/sample_docs via indexer.

    Args:
        store: Target VectorStore instance.
        demo_index_dir: Directory containing index.json and vectors.npz (default: data/demo_index).
        rebuild_fn: Optional callable to invoke if rebuild from sample_docs is required.

    Returns:
        True if loaded from export with 0 API calls (or already in sync), False if rebuilt.
    """
    export_dir = demo_index_dir or DEFAULT_EXPORT_DIR
    json_path = export_dir / "index.json"
    npz_path = export_dir / "vectors.npz"

    # Check if export files exist
    if not json_path.exists() or not npz_path.exists():
        logger.warning(
            "Demo index export files missing in %s. Falling back to building from sample docs.",
            export_dir,
        )
        if rebuild_fn is not None:
            rebuild_fn()
        return False

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            manifest: Dict[str, Any] = json.load(f)
    except Exception as exc:
        logger.warning("Failed reading demo index manifest: %s", exc)
        if rebuild_fn is not None:
            rebuild_fn()
        return False

    expected_model = GEMINI_EMBED_MODEL or "gemini-embedding-001"
    recorded_model = manifest.get("embedding_model", "")
    if recorded_model and expected_model and recorded_model != expected_model:
        logger.warning(
            "Demo index embedding model mismatch (recorded '%s' vs active '%s'). Falling back to rebuilding.",
            recorded_model,
            expected_model,
        )
        if rebuild_fn is not None:
            rebuild_fn()
        return False

    target_fingerprint = manifest.get("fingerprint", "")
    total_chunks = manifest.get("total_chunks", 0)

    # Check if store is already in sync
    if store.count() == total_chunks and store.get_fingerprint() == target_fingerprint:
        logger.debug("Vector store is already in sync with demo index export (fingerprint %s).", target_fingerprint)
        return True

    # Store differs or is empty: load from export with 0 API calls
    logger.info("Importing %d chunks from demo index export with 0 API calls...", total_chunks)

    # Reset collection if not empty
    if store.count() > 0:
        was_read_only = store.read_only
        store.read_only = False
        try:
            store.reset()
        finally:
            store.read_only = was_read_only

    npz = np.load(npz_path)
    vectors = npz["vectors"]

    chunks_data = manifest.get("chunks", [])
    ids: List[str] = [c["id"] for c in chunks_data]
    documents: List[str] = [c["text"] for c in chunks_data]
    metadatas: List[Dict[str, Any]] = [c["metadata"] for c in chunks_data]

    # Convert vectors to float list for Chroma collection add
    embeddings_list = vectors.astype(float).tolist()

    # Batch add into collection in chunks of 100
    batch_size = 100
    for i in range(0, len(ids), batch_size):
        end_idx = min(i + batch_size, len(ids))
        store.collection.add(
            ids=ids[i:end_idx],
            documents=documents[i:end_idx],
            metadatas=metadatas[i:end_idx],
            embeddings=embeddings_list[i:end_idx],
        )

    logger.info("Successfully imported %d chunks into vector store with 0 API calls.", store.count())
    return True
