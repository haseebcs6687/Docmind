"""CLI query interface for DocMind RAG pipeline."""

import logging
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.logging_setup import configure_logging

# Configure logging first to suppress third-party HTTP transport logs
configure_logging()

# Ensure proper stdout encoding on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.config import SCORE_THRESHOLD
from src.rag import answer
from src.vectorstore import VectorStore


def print_response(question: str, resp) -> None:
    """Print a formatted block for a single RAG response."""
    print("=" * 80)
    print(f"Question: {question}")
    print(f"Retrieved: top score = {resp.top_score:.2f} (threshold = {SCORE_THRESHOLD:.2f})")
    print(f"Found: {'Yes' if resp.found else 'No'}")
    print(f"Model Used: {getattr(resp, 'model_used', 'N/A')}")
    print(f"Fallback Used: {'Yes' if getattr(resp, 'fallback_used', False) else 'No'}")
    print(f"Cached: {'Yes' if getattr(resp, 'cached', False) else 'No'}")
    print(f"\nAnswer:\n{resp.answer}\n")

    if resp.found and resp.sources:
        print("Citations:")
        for s in resp.sources:
            score_val = s.get("score", 0.0)
            citation_lbl = s.get("citation", "Unknown")
            snippet = s.get("snippet", "").replace("\n", " ").strip()
            print(f"  - [{citation_lbl}] (score: {score_val:.2f})")
            if snippet:
                print(f'    "{snippet[:150]}..."')
    elif not resp.found:
        print("Citations: None (Answer not found in documents or below score threshold)")

    embed_t = getattr(resp, "embed_ms", 0.0)
    gen_t = getattr(resp, "gen_ms", 0.0)
    rw_t = getattr(resp, "rewrite_ms", 0.0)
    print(f"\nLatency: {resp.latency_ms:.1f} ms (embed: {embed_t:.1f} ms, gen: {gen_t:.1f} ms, rewrite: {rw_t:.1f} ms) | API calls: {resp.api_calls}")
    print("=" * 80)


def main() -> None:
    store = VectorStore()
    doc_count = store.count()
    if doc_count == 0:
        print("Warning: Vector store contains 0 documents.")
        print("Please run 'python scripts/build_index.py' to ingest sample documents first.")
        sys.exit(0)

    # If arguments provided, process them in batch
    args = sys.argv[1:]
    if args:
        for q in args:
            clean_q = q.strip()
            if not clean_q:
                continue
            resp = answer(clean_q, store=store)
            print_response(clean_q, resp)
            print()
        return

    # Otherwise enter interactive loop
    print("DocMind Interactive Query Mode")
    print("Type your question and press Enter. Type 'exit', 'quit', or press Ctrl+C to stop.\n")

    while True:
        try:
            user_input = input("Question > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("Exiting DocMind.")
                break
            resp = answer(user_input, store=store)
            print_response(user_input, resp)
            print()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting DocMind.")
            break
        except Exception as e:
            print(f"Error: {e}\n")


if __name__ == "__main__":
    main()
