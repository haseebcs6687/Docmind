"""CLI script to test semantic retrieval across benchmark queries."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.vectorstore import VectorStore

QUERIES = [
    "What is the initial consultation fee?",
    "What are the office hours on Saturday?",
    "How long are client files kept?",
    "Do you have parking space?",
]


def main() -> None:
    vstore = VectorStore()
    total_chunks = vstore.count()
    if total_chunks == 0:
        print("[Error] Vector store is empty! Please run 'python scripts/build_index.py' first.")
        sys.exit(1)

    print(f"Testing semantic retrieval against {total_chunks} indexed chunks in ChromaDB.\n")

    for idx, q in enumerate(QUERIES, start=1):
        print("=" * 95)
        print(f"Query {idx}: \"{q}\"")
        print("=" * 95)
        results = vstore.query(q, k=3)
        if not results:
            print("  No results found.")
            continue

        print(f"  {'Score':<7} | {'Citation':<35} | {'First 100 Chars'}")
        print("  " + "-" * 91)
        for r in results:
            score_str = f"{r['score']:.4f}"
            citation_str = r["citation"]
            if len(citation_str) > 35:
                citation_str = citation_str[:32] + "..."
            text_preview = r["text"].replace("\n", " ")[:100]
            print(f"  {score_str:<7} | {citation_str:<35} | {text_preview}")
        print()


if __name__ == "__main__":
    main()
