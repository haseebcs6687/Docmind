"""A/B test comparing GEN_THINKING_LEVEL=None (unset) vs GEN_THINKING_LEVEL='MINIMAL'.

Runs 6 calls total: 3 unset vs 3 MINIMAL, interleaved, with 8s pauses between calls.
Evaluates facts matched against MSA_ANSWER_KEY, unverified rows, latency, and model/fallback used.
Applies the literal decision rule to determine whether MINIMAL should be the default.
"""

import os
import sys
import time
from pathlib import Path
import statistics
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import GEMINI_FALLBACK_MODEL, GEMINI_MODEL
from src.contracts import (
    ContractAnalysis,
    ContractAnalysisCache,
    FieldResult,
    analyze_contract,
)
from src.logging_setup import configure_logging
from src.vectorstore import VectorStore
from scripts.check_contracts import MSA_ANSWER_KEY, evaluate_analysis

configure_logging()


def run_ab_test():
    store = VectorStore()
    doc_name = "Master_Services_Agreement_Northgate.pdf"
    units = store.get_source_units(doc_name, allowed_visibility={"client", "staff"})
    if not units:
        print(f"Error: Could not retrieve units for {doc_name}")
        sys.exit(1)

    print("=" * 90)
    print(" A/B TEST: GEN_THINKING_LEVEL UNSET vs MINIMAL")
    print(f" Target Document: {doc_name} ({len(units)} units)")
    print(f" Primary Model   : {GEMINI_MODEL}")
    print(f" Fallback Model  : {GEMINI_FALLBACK_MODEL}")
    print(" Plan            : 6 calls (3 unset vs 3 MINIMAL, interleaved, 8s pause)")
    print("=" * 90)

    configs = ["unset", "MINIMAL", "unset", "MINIMAL", "unset", "MINIMAL"]
    results = []

    for i, cfg in enumerate(configs, start=1):
        print(f"\n--- Run {i}/6: Thinking Level = {cfg} ---")
        if cfg == "unset":
            if "GEN_THINKING_LEVEL" in os.environ:
                del os.environ["GEN_THINKING_LEVEL"]
        else:
            os.environ["GEN_THINKING_LEVEL"] = cfg

        # Fresh cache instance per run to ensure cache is completely bypassed
        fresh_cache = ContractAnalysisCache()

        t_start = time.perf_counter()
        success = False
        error_msg = ""
        analysis = None
        matched_facts = 0
        unverified_rows = 0
        model_used = ""
        fallback_used = False
        latency_ms = 0.0

        try:
            analysis = analyze_contract(
                units=units,
                document_name=doc_name,
                access_mode="staff",
                cache=fresh_cache,
            )
            latency_ms = analysis.latency_ms
            model_used = analysis.model
            fallback_used = bool(model_used and model_used != GEMINI_MODEL)
            success = True

            matched_facts, total_facts, unverified_rows = evaluate_analysis(
                doc_name=doc_name,
                analysis=analysis,
                answer_key=MSA_ANSWER_KEY,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - t_start) * 1000
            error_msg = str(exc)
            print(f"Run {i} ERROR: {error_msg}")

        results.append({
            "run": i,
            "config": cfg,
            "success": success,
            "error": error_msg,
            "latency_ms": latency_ms,
            "model_used": model_used,
            "fallback_used": fallback_used,
            "matched_facts": matched_facts,
            "unverified_rows": unverified_rows,
        })

        if i < len(configs):
            print("Pausing 8s before next call to protect rate limits...", flush=True)
            time.sleep(8)

    # Print Summary Table
    print("\n" + "=" * 90)
    print(" A/B TEST RESULTS SUMMARY")
    print("=" * 90)
    print(f"{'Run':<4} | {'Config':<8} | {'Success':<8} | {'Latency (s)':<12} | {'Model':<22} | {'Fallback':<9} | {'Facts':<8} | {'Unverified'}")
    print("-" * 90)

    for r in results:
        succ_str = "PASS" if r["success"] else "FAIL"
        lat_sec = f"{r['latency_ms'] / 1000.0:.2f}s"
        fb_str = "Yes" if r["fallback_used"] else "No"
        facts_str = f"{r['matched_facts']}/14" if r["success"] else "N/A"
        unv_str = str(r["unverified_rows"]) if r["success"] else "N/A"
        mod_str = r["model_used"] or "-"
        print(f"{r['run']:<4} | {r['config']:<8} | {succ_str:<8} | {lat_sec:<12} | {mod_str:<22} | {fb_str:<9} | {facts_str:<8} | {unv_str}")
    print("=" * 90)

    # Calculate Medians & Failure Counts
    unset_runs = [r for r in results if r["config"] == "unset"]
    min_runs = [r for r in results if r["config"] == "MINIMAL"]

    unset_failures = sum(1 for r in unset_runs if not r["success"])
    min_failures = sum(1 for r in min_runs if not r["success"])

    unset_latencies = [r["latency_ms"] / 1000.0 for r in unset_runs if r["success"]]
    min_latencies = [r["latency_ms"] / 1000.0 for r in min_runs if r["success"]]

    unset_facts = [r["matched_facts"] for r in unset_runs if r["success"]]
    min_facts = [r["matched_facts"] for r in min_runs if r["success"]]

    unset_unv = [r["unverified_rows"] for r in unset_runs if r["success"]]
    min_unv = [r["unverified_rows"] for r in min_runs if r["success"]]

    print("\nSTATISTICAL COMPARISON:")
    print(f"Failures        : unset = {unset_failures}/3, MINIMAL = {min_failures}/3")
    if unset_latencies and min_latencies:
        print(f"Median Latency  : unset = {statistics.median(unset_latencies):.2f}s, MINIMAL = {statistics.median(min_latencies):.2f}s")
    if unset_facts and min_facts:
        print(f"Median Facts    : unset = {statistics.median(unset_facts):.1f}/14, MINIMAL = {statistics.median(min_facts):.1f}/14")
    if unset_unv and min_unv:
        print(f"Median Unverified: unset = {statistics.median(unset_unv):.1f}, MINIMAL = {statistics.median(min_unv):.1f}")

    # Pairwise comparison
    print("\nPAIRWISE COMPARISON:")
    pair_pass = True
    for p in range(3):
        u = unset_runs[p]
        m = min_runs[p]
        pair_num = p + 1
        print(f"\nPair {pair_num} (Run {u['run']} unset vs Run {m['run']} MINIMAL):")

        # Failure check
        u_fail = not u["success"]
        m_fail = not m["success"]
        if m_fail and not u_fail:
            print(f"  Failures    : MINIMAL failed but unset succeeded -> VIOLATION")
            pair_pass = False
        else:
            print(f"  Failures    : unset failed={u_fail}, MINIMAL failed={m_fail} -> OK")

        if not m_fail and not u_fail:
            # Facts check
            facts_ok = m["matched_facts"] >= u["matched_facts"]
            print(f"  Facts       : unset = {u['matched_facts']}, MINIMAL = {m['matched_facts']} -> {'OK' if facts_ok else 'VIOLATION'}")
            if not facts_ok:
                pair_pass = False

            # Unverified check
            unv_ok = m["unverified_rows"] <= u["unverified_rows"]
            print(f"  Unverified  : unset = {u['unverified_rows']}, MINIMAL = {m['unverified_rows']} -> {'OK' if unv_ok else 'VIOLATION'}")
            if not unv_ok:
                pair_pass = False

    total_min_fails_ok = min_failures <= unset_failures
    print("\n" + "=" * 90)
    print(" DECISION RULE EVALUATION")
    print("=" * 90)
    print(f"Rule requirement 1: MINIMAL matched >= facts in EVERY pair: {'PASS' if pair_pass else 'FAIL'}")
    print(f"Rule requirement 2: MINIMAL had <= unverified rows in EVERY pair: {'PASS' if pair_pass else 'FAIL'}")
    print(f"Rule requirement 3: MINIMAL failed no more often: {total_min_fails_ok} ({min_failures} <= {unset_failures})")

    adopt_minimal = pair_pass and total_min_fails_ok
    if adopt_minimal:
        print("\n>>> DECISION: ADOPT 'MINIMAL' as the global default for ALL generation calls.")
    else:
        print("\n>>> DECISION: LEAVE UNSET as the default.")
    print("=" * 90)
    return adopt_minimal


if __name__ == "__main__":
    run_ab_test()
