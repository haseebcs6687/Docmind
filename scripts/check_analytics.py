"""Live verification script for Knowledge Insights & Analytics engine."""

import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analytics import AnalyticsStore, gaps_to_csv, redact_pii
from src.logging_setup import configure_logging

configure_logging()


def verify_analytics():
    print("=" * 80)
    print(" LIVE VERIFICATION: KNOWLEDGE INSIGHTS & ANALYTICS")
    print("=" * 80)

    # 1. Temporary Database Test
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        temp_db = os.path.join(tmpdir, "test_verify.db")
        print(f"\n1. Testing temporary store at: {temp_db}")
        temp_store = AnalyticsStore(db_path=temp_db)

        # Log 3 dummy events
        temp_store.safe_log(
            session_id="verify_s1",
            audience="client",
            kind="answered",
            question="What is the fee? Call me at 0300-1234567 or partner@law.pk",
            top_source="Fee_Schedule_2026.pdf, p. 1",
            top_score=0.88,
            cited_sources=["Fee_Schedule_2026.pdf, p. 1"],
            latency_ms=1200.0,
        )
        temp_store.safe_log(
            session_id="verify_s1",
            audience="client",
            kind="not_found",
            reason="below_threshold",
            question="How do I file tax returns with FBR?",
            top_source="Client_FAQ.txt",
            top_score=0.48,
            latency_ms=850.0,
            vector=[0.1, 0.2, 0.3],
        )
        temp_store.safe_log(
            session_id="verify_s2",
            audience="staff",
            kind="answered",
            question="What is the conflict check SOP?",
            top_source="Client_Intake_SOP.pdf, p. 2",
            top_score=0.92,
            cited_sources=["Client_Intake_SOP.pdf, p. 2"],
            latency_ms=950.0,
        )

        counts = temp_store.count()
        print(f"   Logged events: {counts['total']} (live: {counts['live']}, synthetic: {counts['synthetic']})")
        assert counts["total"] == 3, f"Expected 3 events, got {counts['total']}"

        summary = temp_store.summary(access_mode="staff", period_days=7)
        print(f"   Summary total: {summary.total_queries}")
        print(f"   Answer rate  : {summary.answer_rate:.1f}%")
        print(f"   Gaps found   : {len(summary.gaps)}")
        assert summary.total_queries == 3
        assert summary.answered_queries == 2
        assert summary.not_found_queries == 1
        assert len(summary.gaps) >= 1

        # Test CSV generation
        csv_out = gaps_to_csv(summary.gaps)
        assert "Cluster ID" in csv_out
        assert "Representative Question" in csv_out
        print("   CSV export   : PASSED (valid columns and headers)")

        print("   Temporary DB verification: ALL CHECKS PASSED.")

    # 2. Real Database Seeding & Verification
    real_db_path = "data/analytics.db"
    print(f"\n2. Loading demo activity seed into real store: {real_db_path}")
    real_store = AnalyticsStore(db_path=real_db_path)

    # Clear prior synthetic data to ensure clean state
    cleared = real_store.clear_synthetic()
    if cleared > 0:
        print(f"   Cleared {cleared} prior synthetic events.")

    loaded = real_store.load_seed("data/demo_activity")
    print(f"   Loaded {loaded} synthetic events over past 14 business days.")

    real_counts = real_store.count()
    print(f"   Total DB events: {real_counts['total']} (live: {real_counts['live']}, synthetic: {real_counts['synthetic']})")

    real_summary = real_store.summary(access_mode="staff", period_days=14)
    print("\n" + "=" * 80)
    print(" 14-DAY ANALYTICS SUMMARY (REAL DATABASE)")
    print("=" * 80)
    print(f"Total Queries         : {real_summary.total_queries}")
    print(f"Answered Queries      : {real_summary.answered_queries} ({real_summary.answer_rate:.1f}%)")
    print(f"Knowledge Gap Queries : {real_summary.not_found_queries}")
    print(f"Knowledge Gap Clusters: {len(real_summary.gaps)}")
    print(f"Cache Hit Rate        : {real_summary.cache_hit_rate:.1f}%")
    print(f"Average Latency       : {real_summary.avg_latency_ms / 1000.0:.2f}s")
    print(f"Daily Series Days     : {len(real_summary.daily_series)}")
    print("-" * 80)
    print("Top Knowledge Gaps:")
    for g in real_summary.gaps[:5]:
        print(f"  #{g['cluster_id']}: '{g['representative_query']}' (count: {g['count']}, sim: {g['avg_top_score']:.2f}, action: {g['suggested_action']})")
    print("-" * 80)
    print("Most Asked Questions:")
    for q in real_summary.top_questions[:5]:
        print(f"  Asked {q['count']}x: '{q['question']}' ({q['audience']})")
    print("=" * 80)

    assert real_summary.total_queries >= 100, f"Expected >= 100 queries, got {real_summary.total_queries}"
    assert len(real_summary.gaps) >= 3, f"Expected >= 3 gap clusters, got {len(real_summary.gaps)}"
    assert real_summary.answer_rate > 70.0, f"Expected > 70% answer rate, got {real_summary.answer_rate}"
    print("\nALL LIVE ANALYTICS VERIFICATIONS COMPLETED SUCCESSFULLY!")


if __name__ == "__main__":
    verify_analytics()
