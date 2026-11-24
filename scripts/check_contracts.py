"""Live verification script for contract key-terms analysis and citation verification."""

import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Default thinking level (unset as determined by A/B evaluation)
# os.environ["GEN_THINKING_LEVEL"] = "MINIMAL"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.contracts import ContractAnalysis, FieldResult, analyze_contract
from src.logging_setup import configure_logging
from src.vectorstore import VectorStore

configure_logging()


def normalize(s: str) -> str:
    """Normalize string for fuzzy evaluation: lowercase, punctuation stripped, whitespace collapsed."""
    s = (s or "").lower()
    s = re.sub(r"[^\w\s%]", " ", s)
    return " ".join(s.split())


# Expected Answer Key for MSA
MSA_ANSWER_KEY: Dict[str, Optional[List[str]]] = {
    "contract_type": ["master services agreement"],
    "parties": ["northgate logistics", "brightline"],
    "effective_date": ["1 march 2026"],
    "term": ["24 months"],
    "renewal": ["12 month"],
    "payment": ["450 000"],
    "late_payment": ["1 5%"],
    "termination": ["90 days", "30"],
    "liability": ["12 months"],
    "confidentiality": ["5 years"],
    "governing_law": ["pakistan"],
    "dispute_resolution": ["arbitration", "lahore"],
    "signatories": ["bilal ahmed", "sana iqbal"],
    "force_majeure": None,  # Expected NOT STATED
}

# Expected Answer Key for Lease
LEASE_ANSWER_KEY: Dict[str, Optional[List[str]]] = {
    "contract_type": ["lease"],
    "parties": ["imran qureshi", "crescent textiles"],
    "effective_date": ["1 april 2026"],
    "term": ["3 years"],
    "renewal": None,  # Expected NOT STATED
    "payment": ["380 000"],
    "late_payment": ["5 000"],
    "termination": ["60 days"],
    "liability": None,  # Expected NOT STATED
    "confidentiality": None,  # Expected NOT STATED
    "governing_law": ["pakistan"],
    "dispute_resolution": ["lahore"],
    "signatories": ["imran qureshi", "danish rehman"],
    "force_majeure": None,  # Expected NOT STATED
}


def evaluate_analysis(
    doc_name: str,
    analysis: ContractAnalysis,
    answer_key: Dict[str, Optional[List[str]]],
) -> Tuple[int, int, int]:
    """Evaluate extracted field results against answer key and print detailed table."""
    print("\n" + "=" * 105)
    print(f" CONTRACT ANALYSIS: {doc_name}")
    print(f" Latency: {analysis.latency_ms:.1f} ms | Model: {analysis.model} | API calls: {analysis.api_calls} | Cached: {analysis.cached}")
    print("=" * 105)
    print(f"{'Field':<20} | {'Status':<11} | {'Citation':<38} | {'Eval':<6} | {'Extracted Value'}")
    print("-" * 105)

    passed_checks = 0
    total_checks = len(answer_key)
    unverified_count = 0

    f_map = {f.key: f for f in analysis.fields}

    for key, expected_keywords in answer_key.items():
        f = f_map.get(key)
        if not f:
            print(f"{key:<20} | {'MISSING':<11} | {'-':<38} | {'FAIL':<6} | Key not present in results")
            continue

        if f.status == "Unverified":
            unverified_count += 1

        norm_val = normalize(f.value)

        if expected_keywords is None:
            # Expected NOT STATED
            is_pass = (not f.found) and (f.status == "Not stated")
            eval_label = "PASS" if is_pass else "FAIL"
            if is_pass:
                passed_checks += 1
            disp_val = "[Not stated in document]" if is_pass else f"UNEXPECTED: {f.value[:40]}"
        else:
            # Expected found with keywords
            is_pass = f.found and (f.status in ("Quote verified", "Verified")) and all(kw in norm_val for kw in expected_keywords)
            eval_label = "PASS" if is_pass else "FAIL"
            if is_pass:
                passed_checks += 1
            disp_val = f.value[:45] + ("..." if len(f.value) > 45 else "")

        cit_disp = f.citation[:38] if f.citation else "-"
        print(f"{f.label:<20} | {f.status:<11} | {cit_disp:<38} | {eval_label:<6} | {disp_val}")
        if f.status == "Unverified" and f.found:
            print(f"  --> Unverified Quote: '{f.quote}'")

    print("-" * 105)
    pct = (passed_checks / total_checks) * 100
    print(f"Score: {passed_checks}/{total_checks} ({pct:.1f}%) | Unverified Count: {unverified_count}")
    print("=" * 105)

    return passed_checks, total_checks, unverified_count


def main():
    store = VectorStore()
    print("Loading indexed contract units from vector store in Staff mode...")

    # 1. Analyze MSA
    msa_name = "Master_Services_Agreement_Northgate.pdf"
    msa_units = store.get_source_units(msa_name, allowed_visibility={"client", "staff"})
    if not msa_units:
        print(f"Error: Could not retrieve units for {msa_name}")
        sys.exit(1)
    print(f"Retrieved {len(msa_units)} units for {msa_name}.")

    print("Pausing 10 seconds before analysis to ensure clear rate limits...", flush=True)
    time.sleep(10)
    print(f"Calling Gemini to analyze {msa_name}...", flush=True)
    msa_analysis = analyze_contract(msa_units, msa_name, access_mode="staff")
    p1, t1, u1 = evaluate_analysis(msa_name, msa_analysis, MSA_ANSWER_KEY)

    # 2. Analyze Lease
    lease_name = "Commercial_Lease_Agreement_Gulberg_Office.docx"
    lease_units = store.get_source_units(lease_name, allowed_visibility={"client", "staff"})
    if not lease_units:
        print(f"Error: Could not retrieve units for {lease_name}")
        sys.exit(1)
    print(f"Retrieved {len(lease_units)} units for {lease_name}.", flush=True)

    print("Pausing 10 seconds between contract analyses to avoid backend rate limiting...", flush=True)
    time.sleep(10)
    print(f"Calling Gemini to analyze {lease_name}...", flush=True)
    lease_analysis = analyze_contract(lease_units, lease_name, access_mode="staff")
    p2, t2, u2 = evaluate_analysis(lease_name, lease_analysis, LEASE_ANSWER_KEY)

    # 3. Test In-Process Live Cache Hit
    print("\n" + "=" * 80)
    print(" LIVE CACHE VERIFICATION")
    print("=" * 80)
    print(f"Re-analyzing {msa_name} in the same process to test cache hit...")
    t_cache_start = time.perf_counter()
    msa_cached = analyze_contract(msa_units, msa_name, access_mode="staff")
    t_cache_elapsed_ms = (time.perf_counter() - t_cache_start) * 1000

    print(f"Cached Flag : {msa_cached.cached}")
    print(f"API Calls   : {msa_cached.api_calls}")
    print(f"Elapsed Time: {t_cache_elapsed_ms:.2f} ms")
    print(f"Identical   : {msa_cached.fields == msa_analysis.fields}")

    assert msa_cached.cached is True, "Expected cached=True on repeat analysis"
    assert msa_cached.api_calls == 0, "Expected api_calls=0 on repeat analysis"
    assert msa_cached.fields == msa_analysis.fields, "Expected identical fields from cache"
    print("Cache verification PASSED (100% identical, 0 API calls)!")

    # Overall summary
    total_passed = p1 + p2
    total_evals = t1 + t2
    total_unverified = u1 + u2
    overall_pct = (total_passed / total_evals) * 100

    print("\n" + "=" * 80)
    print(" LIVE VERIFICATION SUMMARY")
    print("=" * 80)
    print(f"Total Terms Evaluated : {total_evals}")
    print(f"Total Terms Passed    : {total_passed} ({overall_pct:.1f}%)")
    print(f"Total Unverified Terms: {total_unverified}")
    print("=" * 80)

    if total_unverified > 0 or overall_pct < 85.0:
        print("Verification finished with warnings.")
    else:
        print("ALL LIVE VERIFICATIONS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
