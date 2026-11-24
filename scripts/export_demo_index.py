"""Export the 8 sample documents index from Chroma collection to data/demo_index/ with zero API calls needed for import."""

import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Dict, Optional

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import GEMINI_EMBED_MODEL
from src.vectorstore import VectorStore


def compute_file_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def export_demo_index(
    output_dir: Optional[Path] = None,
    store: Optional[VectorStore] = None,
) -> None:
    target_dir = output_dir or (PROJECT_ROOT / "data" / "demo_index")
    target_dir.mkdir(parents=True, exist_ok=True)

    vstore = store or VectorStore()
    total_count = vstore.count()
    if total_count == 0:
        print("ERROR: Vector store is empty! Cannot export demo index.")
        sys.exit(1)

    print(f"Exporting {total_count} chunks from vector store...")

    data = vstore.collection.get(include=["documents", "metadatas", "embeddings"])
    ids = list(data["ids"])
    documents = list(data["documents"])
    metadatas = list(data["metadatas"])
    embeddings = np.array(data["embeddings"], dtype=np.float32)

    # Compute source file hashes from data/sample_docs
    sample_docs_dir = PROJECT_ROOT / "data" / "sample_docs"
    source_hashes: Dict[str, str] = {}
    for p in sample_docs_dir.iterdir():
        if p.is_file() and p.name not in (".gitkeep", "manifest.json"):
            source_hashes[p.name] = compute_file_sha256(p)

    fingerprint = vstore.get_fingerprint()

    index_manifest = {
        "embedding_model": GEMINI_EMBED_MODEL or "gemini-embedding-001",
        "fingerprint": fingerprint,
        "total_chunks": len(ids),
        "source_hashes": source_hashes,
        "chunks": [
            {
                "id": cid,
                "text": text,
                "metadata": meta,
            }
            for cid, text, meta in zip(ids, documents, metadatas)
        ],
    }

    json_path = target_dir / "index.json"
    npz_path = target_dir / "vectors.npz"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(index_manifest, f, indent=2)

    np.savez_compressed(npz_path, vectors=embeddings, ids=np.array(ids))

    json_size_kb = json_path.stat().st_size / 1024
    npz_size_kb = npz_path.stat().st_size / 1024
    total_mb = (json_path.stat().st_size + npz_path.stat().st_size) / (1024 * 1024)

    print("=== Demo Index Export Complete ===")
    print(f"Chunks exported   : {len(ids)}")
    print(f"Sources exported  : {len(source_hashes)}")
    print(f"Fingerprint       : {fingerprint}")
    print(f"index.json size   : {json_size_kb:.1f} KB ({json_path})")
    print(f"vectors.npz size  : {npz_size_kb:.1f} KB ({npz_path})")
    print(f"Total export size : {total_mb:.2f} MB")


if __name__ == "__main__":
    from typing import Optional
    export_demo_index()
