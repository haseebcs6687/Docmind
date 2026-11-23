"""CLI script to build the persistent ChromaDB index from data/sample_docs."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.logging_setup import configure_logging

configure_logging()

from src.loaders import load_directory
from src.vectorstore import VectorStore

SAMPLE_DIR = PROJECT_ROOT / "data" / "sample_docs"


def compute_file_hashes(directory: Path) -> dict:
    hashes = {}
    for f in directory.iterdir():
        if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in (".pdf", ".docx", ".txt"):
            hashes[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
    return hashes


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ChromaDB index for DocMind documents.")
    parser.add_argument("--rebuild", action="store_true", help="Reset and rebuild the entire index from scratch.")
    parser.add_argument("--dir", type=str, default=str(SAMPLE_DIR), help="Directory of documents to index.")
    args = parser.parse_args()

    doc_dir = Path(args.dir)
    print(f"Loading documents from: {doc_dir}")
    units, load_report = load_directory(doc_dir)
    print(f"Loaded {len(load_report['loaded_files'])} files ({load_report['total_units']} text units).\n")

    vstore = VectorStore()

    if args.rebuild:
        print("Resetting vector store index (--rebuild flag specified)...")
        vstore.reset()

    file_hashes = compute_file_hashes(doc_dir)

    manifest_data = {}
    manifest_file = doc_dir / "manifest.json"
    if manifest_file.exists():
        try:
            with open(manifest_file, "r", encoding="utf-8") as mf:
                manifest_data = json.load(mf)
        except Exception as e:
            print(f"Warning: Failed to load manifest.json: {e}")

    print("Indexing documents into ChromaDB...")
    index_report = vstore.index_units(units, file_hashes, metadata_by_source=manifest_data)

    print("\n" + "=" * 80)
    print(" INDEXING SUMMARY")
    print("=" * 80)
    if index_report["skipped_files"]:
        print(f"Skipped (already indexed & unchanged): {len(index_report['skipped_files'])} file(s)")
        for sf in index_report["skipped_files"]:
            print(f"  - {sf} (hash unchanged)")

    if index_report["indexed_files"]:
        print(f"\nIndexed: {len(index_report['indexed_files'])} file(s)")
        sources_info = vstore.list_sources()
        for s in sources_info:
            if s["name"] in index_report["indexed_files"]:
                print(f"  - {s['name']:<40} : {s['chunk_count']} chunks")
    else:
        print("\nAll files were already indexed, 0 embedding calls made.")

    print("-" * 80)
    print(f"Total Chunks Stored in Vector DB : {vstore.count()}")
    print(f"Total Embedding API Requests Made : {index_report['embedding_calls']}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
