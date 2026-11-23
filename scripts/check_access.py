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
        # Staff Contract Queries (Step 12 additions)
        ("What are the governing law and dispute resolution terms in the Northgate MSA?", "Staff Contract: MSA"),
        ("What is the monthly rent and security deposit for the Gulberg office lease?", "Staff Contract: Lease"),
    ]

    staff_only_sources = {
        "Master_Services_Agreement_Northgate.pdf",
        "Commercial_Lease_Agreement_Gulberg_Office.docx",
        "Client_Intake_SOP.pdf",
        "Confidentiality_and_Data_Policy.pdf",
    }

    print("\n" + "=" * 115)
    print(f"{'Category':<22} | {'Mode':<7} | {'Top Source':<36} | {'Score':<6} | {'Vis':<7} | {'Practice Area':<15}")
    print("=" * 115)

    leaks_detected = []
    for query, category in test_queries:
        for mode in ("client", "staff"):
            allowed = {"client"} if mode == "client" else {"client", "staff"}
            results = store.query(query, k=3, allowed_visibility=allowed)

            # In client mode, verify zero chunks from staff-only sources
            if mode == "client":
                for res in results:
                    src_name = res.get("source", "")
                    if src_name in staff_only_sources or res.get("visibility") == "staff":
                        leaks_detected.append((category, query, src_name))

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

    if leaks_detected:
        print(f"\n[FAIL] Access leak detected in Client mode ({len(leaks_detected)} instances):")
        for cat, q, s in leaks_detected:
            print(f"  - [{cat}] '{q}' returned staff source: '{s}'")
        sys.exit(1)
    else:
        print("\n[PASS] Strict visibility boundary verified: ZERO staff-only chunks returned in Client mode across all queries.")


if __name__ == "__main__":
    main()
