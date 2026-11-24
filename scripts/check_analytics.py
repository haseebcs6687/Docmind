"""Live verification script for Knowledge Insights & Analytics engine."""

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analytics import (
    AnalyticsAccessError,
    AnalyticsStore,
    blob_to_vector,
    gaps_to_csv,
    redact_pii,
)
from src.config import GAP_CLUSTER_COSINE
from src.logging_setup import configure_logging
from src.rag import ChatSession
from src.vectorstore import VectorStore

configure_logging()


def verify_analytics():
    print("=" * 85)
    print(" LIVE VERIFICATION: KNOWLEDGE INSIGHTS & ANALYTICS (G2 EVIDENCE)")
    print("=" * 85)

    # 1. Temporary Database Test
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        temp_db = os.path.join(tmpdir, "test_analytics_temp.db")
        print(f"\n[1] INITIALIZING TEMP STORE: {temp_db}")
        temp_store = AnalyticsStore(db_path=temp_db)

        # Load seed vectors for parking trio and wallet pair
        seed_vec_path = PROJECT_ROOT / "data" / "demo_activity" / "seed_vectors.npz"
        vec_dict = np.load(seed_vec_path) if seed_vec_path.exists() else {}

        # Log events into temp store
        # E1: Redaction test event (PII)
        pii_raw = "What is the consultation fee? Contact me at 0300-1234567 or partner@law.pk."
        temp_store.safe_log(
            session_id="sess_pii",
            audience="client",
            kind="answered",
            question=pii_raw,
            top_source="Fee_Schedule_2026.pdf, p. 1",
            top_score=0.88,
            cited_sources=["Fee_Schedule_2026.pdf, p. 1"],
            latency_ms=1450.0,
        )

        # E2, E3, E4: Parking trio events (with embeddings)
        park_q1 = "Is there on-site vehicle parking available for visitors?"
        park_q2 = "Where can motorists park their vehicles when arriving for an appointment?"
        park_q3 = "Is dedicated visitor vehicle parking space provided on the premises?"

        temp_store.safe_log(
            session_id="sess_park1",
            audience="client",
            kind="not_found",
            reason="below_threshold",
            question=park_q1,
            top_source="Client_FAQ.txt, Overview",
            top_score=0.608,
            latency_ms=2100.0,
            vector=vec_dict.get("c_nf_park_1"),
        )
        temp_store.safe_log(
            session_id="sess_park2",
            audience="client",
            kind="not_found",
            reason="below_threshold",
            question=park_q2,
            top_source="Practice_Areas_Brochure.pdf, p. 3",
            top_score=0.606,
            latency_ms=1950.0,
            vector=vec_dict.get("c_nf_park_2"),
        )
        temp_store.safe_log(
            session_id="sess_park3",
            audience="client",
            kind="not_found",
            reason="below_threshold",
            question=park_q3,
            top_source="Client_FAQ.txt, Overview",
            top_score=0.624,
            latency_ms=2300.0,
            vector=vec_dict.get("c_nf_park_3"),
        )

        # E5: Mobile wallet not-found event
        wallet_q1 = "Can I settle bills using digital wallets like JazzCash or Nayapay?"
        temp_store.safe_log(
            session_id="sess_wallet",
            audience="client",
            kind="not_found",
            reason="below_threshold",
            question=wallet_q1,
            top_source="Client_FAQ.txt, Q&A 15",
            top_score=0.637,
            latency_ms=1800.0,
            vector=vec_dict.get("c_nf_wallet_1"),
        )

        # E6: Staff answered event
        temp_store.safe_log(
            session_id="sess_staff",
            audience="staff",
            kind="answered",
            question="What is the mandatory file retention period for closed matters?",
            top_source="Confidentiality_and_Data_Policy.pdf, p. 2",
            top_score=0.750,
            cited_sources=["Confidentiality_and_Data_Policy.pdf, p. 2"],
            latency_ms=1600.0,
        )

        # E7 & E8: Run <= 2 live RAG generation calls with logging enabled to temp store
        print("\n[2] RUNNING END-TO-END RAG CALL WITH TEMP STORE LOGGING (<= 2 calls):")
        doc_store = VectorStore()
        session = ChatSession(
            access_mode="client",
            analytics=temp_store,
            store=doc_store,
            cooldown_seconds=0.0,
        )
        rag_resp1 = session.ask("Under what condition is the consultation fee waived?")
        print(f"   Live RAG 1 Answered: {rag_resp1.sources[:1]} (latency: {rag_resp1.latency_ms:.0f}ms)")

        rag_resp2 = session.ask("Do you offer visitor car parking on the premises?")
        print(f"   Live RAG 2 Not-Found: expected_found={rag_resp2.found} (latency: {rag_resp2.latency_ms:.0f}ms)")

        # 3. Print Stored Rows from TEMP Database
        print("\n[3] STORED ROWS IN TEMP DATABASE:")
        print("-" * 115)
        print(f"{'Question':<42} | {'Kind':<10} | {'Reason':<15} | {'Cached':<6} | {'Top Source':<20} | {'Score':<5} | {'Vec'}")
        print("-" * 115)

        with temp_store._get_connection() as conn:
            rows = conn.execute("SELECT * FROM events ORDER BY id ASC").fetchall()
            for r in rows:
                q_disp = r["question"][:40] + (".." if len(r["question"]) > 40 else "")
                src_disp = (r["top_source"] or "")[:20]
                has_vec = bool(r["vec"])
                cached_str = "Yes" if r["cached"] else "No"
                score_str = f"{r['top_score']:.3f}" if r["top_score"] else "0.000"
                reason_str = r["reason"] or "-"
                print(f"{q_disp:<42} | {r['kind']:<10} | {reason_str:<15} | {cached_str:<6} | {src_disp:<20} | {score_str:<5} | {has_vec}")

        print("-" * 115)

        # 4. Redaction Proof
        print("\n[4] REDACTION PROOF:")
        pii_row = rows[0]
        print(f"   Original Question: '{pii_raw}'")
        print(f"   Stored Question  : '{pii_row['question']}'")
        assert "0300-1234567" not in pii_row["question"], "Phone number not redacted!"
        assert "partner@law.pk" not in pii_row["question"], "Email not redacted!"
        assert "[phone]" in pii_row["question"].lower() or "[redacted]" in pii_row["question"].lower(), "Missing phone redaction placeholder!"
        assert "[email]" in pii_row["question"].lower() or "[redacted]" in pii_row["question"].lower(), "Missing email redaction placeholder!"
        print("   Redaction Status : PASSED (Phone and Email successfully redacted).")

        # 5. Parking Grouping with Actual Cosines
        print("\n[5] PARKING GROUPING & PAIRWISE COSINES:")
        v1 = vec_dict.get("c_nf_park_1").astype(np.float32)
        v2 = vec_dict.get("c_nf_park_2").astype(np.float32)
        v3 = vec_dict.get("c_nf_park_3").astype(np.float32)

        cos_12 = float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))
        cos_23 = float(np.dot(v2, v3) / (np.linalg.norm(v2) * np.linalg.norm(v3)))
        cos_13 = float(np.dot(v1, v3) / (np.linalg.norm(v1) * np.linalg.norm(v3)))

        print(f"   Parking Q1 <-> Q2 Cosine: {cos_12:.4f}")
        print(f"   Parking Q2 <-> Q3 Cosine: {cos_23:.4f}")
        print(f"   Parking Q1 <-> Q3 Cosine: {cos_13:.4f}")
        print(f"   Effective GAP_CLUSTER_COSINE: {GAP_CLUSTER_COSINE:.2f}")

        summary = temp_store.summary(access_mode="staff", period_days=7)
        print(f"   Total Clusters Formed: {len(summary.gaps)}")
        for g in summary.gaps:
            print(f"   Cluster #{g['cluster_id']}: '{g['representative_query']}' (count: {g['count']})")
            for sq in g["sample_queries"]:
                print(f"     * {sq}")

        parking_cluster = next((g for g in summary.gaps if "park" in g["representative_query"].lower()), None)
        assert parking_cluster is not None, "Parking questions failed to form a cluster!"
        assert parking_cluster["count"] >= 3, f"Expected >= 3 items in parking cluster, got {parking_cluster['count']}"
        print("   Parking Cluster Verification: PASSED (All parking variants grouped together).")

        # 6. Client-mode Summary Refusal Denial
        print("\n[6] CLIENT-MODE SUMMARY REFUSAL CHECK:")
        refusal_caught = False
        try:
            temp_store.summary(access_mode="client")
        except AnalyticsAccessError as e:
            refusal_caught = True
            print(f"   Refusal Status : REJECTED AS EXPECTED (403 Forbidden)")
            print(f"   Error Message  : '{e}'")

        assert refusal_caught, "Client mode was NOT refused summary access!"

        # 7. CSV Export Verification
        csv_out = gaps_to_csv(summary.gaps)
        assert "Cluster ID" in csv_out
        assert "Representative Question" in csv_out
        print("\n[7] CSV EXPORT: PASSED")

    print("\n" + "=" * 85)
    print(" ALL LIVE ANALYTICS (G2 EVIDENCE) CHECKS PASSED PERFECTLY!")
    print("=" * 85)


if __name__ == "__main__":
    verify_analytics()
