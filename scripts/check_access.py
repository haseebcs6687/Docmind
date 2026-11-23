"""Retrieval-only access check script verifying document visibility boundaries (0 generation calls)."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.logging_setup import configure_logging
from src.vectorstore import VectorStore

configure_logging()


def main():
    store = VectorStore()
    doc_count = store.count()
    print(f"Store chunk count: {doc_count}")

    test_queries = [
        # Canary Queries
        ("Who is the Data Protection Officer and what are their duties?", "Canary 1: DPO"),
        ("What encryption standard is used for client confidential data?", "Canary 2: AES-256"),
        ("What are the Tier 1 Frontline intake procedures?", "Canary 3: Tier 1 Frontline"),
        # Staff Starters
        ("What steps do staff follow during client intake?", "Staff Starter 1"),
        ("How long does the conflict check take?", "Staff Starter 2"),
        ("How quickly must a data breach be reported internally?", "Staff Starter 3"),
        ("Who do I escalate a client dispute to?", "Staff Starter 4"),
        # Client Starters
        ("What is the initial consultation fee?", "Client Starter 1"),
        ("What happens if an invoice is paid late?", "Client Starter 2"),
        ("How long are client files kept?", "Client Starter 3"),
        ("What are your office hours?", "Client Starter 4"),
    ]

    print("\n" + "=" * 115)
    print(f"{'Category':<22} | {'Mode':<7} | {'Top Source':<36} | {'Score':<6} | {'Vis':<7} | {'Practice Area':<15}")
    print("=" * 115)

    for query, category in test_queries:
        for mode in ("client", "staff"):
            allowed = {"client"} if mode == "client" else {"client", "staff"}
            results = store.query(query, k=3, allowed_visibility=allowed)

            if results:
                top = results[0]
                src = top.get("source", "None")[:35]
                score = f"{top.get('score', 0.0):.4f}"
                vis = top.get("visibility", "unknown")
                pa = top.get("practice_area", "unknown")[:15]
            else:
                src = "NO_RESULTS"
                score = "0.0000"
                vis = "-"
                pa = "-"

            print(f"{category:<22} | {mode.capitalize():<7} | {src:<36} | {score:<6} | {vis:<7} | {pa:<15}")
        print("-" * 115)


if __name__ == "__main__":
    main()
