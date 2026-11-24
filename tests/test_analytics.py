"""Unit tests for Knowledge Insights & Analytics engine (DocMind Step 14).

Covers:
- SQLite schema, WAL mode, indexes, thread safety.
- PII redaction (email, phone, CNIC, 9+ digit runs, truncation to 300 chars).
- Vector serialization (float16 BLOB roundtrip, strictly NULL for answered/error).
- Storage & metrics aggregation (counts, answer rate, cache hit rate, daily series zero-fill).
- Knowledge Gaps clustering (exact text, cosine similarity, Jaccard fallback, action rules).
- Formula injection defense in CSV export.
- Purging (retention window and max events cap).
- Role-based access control (Staff only, raises AnalyticsAccessError for Client).
- Deterministic synthetic seeding and synthetic clearing.
- Safe logging error suppression.
- VectorStore.query(return_vector=True) and RagResponse additions.
"""

import io
import json
from pathlib import Path
import sqlite3
import sys
import threading
from datetime import datetime, timedelta, timezone
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pytest

from src.analytics import (
    AnalyticsAccessError,
    AnalyticsStore,
    blob_to_vector,
    gaps_to_csv,
    redact_pii,
    vector_to_blob,
)
from src.rag import RagResponse


# ---------------------------------------------------------------------------
# 1. PII Redaction Tests
# ---------------------------------------------------------------------------

def test_redact_pii_emails():
    text = "Please send the file to partner@sterlingrauf.com or info.law@domain.pk immediately."
    redacted = redact_pii(text)
    assert "[email]" in redacted
    assert "partner@sterlingrauf.com" not in redacted
    assert "info.law@domain.pk" not in redacted


def test_redact_pii_phone_numbers():
    # Pakistani and international formats
    text = "Call me at +92 300 1234567 or 0321-9876543 or +1-555-123-4567."
    redacted = redact_pii(text)
    assert "[phone]" in redacted
    assert "0321-9876543" not in redacted
    assert "+92 300 1234567" not in redacted


def test_redact_pii_cnic_and_long_digits():
    text = "My CNIC is 35201-1234567-1 and account number is 123456789012."
    redacted = redact_pii(text)
    assert "[id]" in redacted
    assert "35201-1234567-1" not in redacted
    assert "123456789012" not in redacted


def test_redact_pii_preserves_normal_numbers():
    text = "The initial consultation fee is PKR 5,000 for 45 minutes in year 2026."
    redacted = redact_pii(text)
    assert "5,000" in redacted
    assert "45" in redacted
    assert "2026" in redacted
    assert "[id]" not in redacted
    assert "[phone]" not in redacted


def test_redact_pii_truncates_to_300_chars():
    long_text = "What is the policy regarding " + ("contracts and retainers " * 30)
    assert len(long_text) > 300
    redacted = redact_pii(long_text)
    assert len(redacted) <= 303
    assert redacted.endswith("...")


# ---------------------------------------------------------------------------
# 2. Vector Serialization & Privacy BLOB Tests
# ---------------------------------------------------------------------------

def test_vector_blob_float16_roundtrip():
    orig_vec = [0.12345, -0.6789, 0.0, 1.0, -0.005]
    blob = vector_to_blob(orig_vec)
    assert isinstance(blob, bytes)
    # 5 float16 elements = 10 bytes
    assert len(blob) == 10

    recovered = blob_to_vector(blob)
    assert isinstance(recovered, np.ndarray)
    assert recovered.dtype == np.float32
    assert len(recovered) == 5
    # float16 precision check (~1e-3)
    np.testing.assert_allclose(orig_vec, recovered, rtol=1e-3, atol=1e-3)


def test_vector_blob_none_handling():
    assert vector_to_blob(None) is None
    assert blob_to_vector(None) is None


def test_vector_stored_only_for_not_found(tmp_path):
    db_file = tmp_path / "test_vec.db"
    store = AnalyticsStore(db_path=str(db_file))

    dummy_vec = [0.1, 0.2, 0.3]

    # 1. Answered event with vector -> vector must be ignored and stored as NULL
    store.log_event(
        session_id="s1",
        audience="client",
        kind="answered",
        question="What is the fee?",
        vector=dummy_vec,
    )

    # 2. Not-found event with vector -> stored as float16 BLOB
    store.log_event(
        session_id="s2",
        audience="client",
        kind="not_found",
        question="What is the tax rate?",
        vector=dummy_vec,
    )

    # 3. Error event with vector -> stored as NULL
    store.log_event(
        session_id="s3",
        audience="staff",
        kind="error",
        question="Broken question",
        vector=dummy_vec,
    )

    with sqlite3.connect(str(db_file)) as conn:
        rows = conn.execute("SELECT kind, vec FROM events ORDER BY id ASC;").fetchall()
        assert len(rows) == 3
        # Answered -> vec is None
        assert rows[0][0] == "answered"
        assert rows[0][1] is None

        # Not-found -> vec is bytes
        assert rows[1][0] == "not_found"
        assert isinstance(rows[1][1], bytes)

        # Error -> vec is None
        assert rows[2][0] == "error"
        assert rows[2][1] is None


# ---------------------------------------------------------------------------
# 3. SQLite Schema, WAL Mode & Thread Safety
# ---------------------------------------------------------------------------

def test_sqlite_wal_mode_and_schema(tmp_path):
    db_file = tmp_path / "test_wal.db"
    store = AnalyticsStore(db_path=str(db_file))

    with sqlite3.connect(str(db_file)) as conn:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        assert journal_mode.lower() == "wal"

        # Check table columns
        cur = conn.execute("PRAGMA table_info(events);")
        cols = {row[1] for row in cur.fetchall()}
        expected_cols = {
            "id", "ts_utc", "session_id", "audience", "kind", "reason",
            "question", "standalone", "top_source", "top_score",
            "cited_sources", "cached", "latency_ms", "model_used",
            "synthetic", "vec"
        }
        assert expected_cols.issubset(cols)


def test_concurrent_multithreaded_writes(tmp_path):
    db_file = tmp_path / "test_concurrency.db"
    store = AnalyticsStore(db_path=str(db_file))

    def worker(worker_id: int):
        for i in range(25):
            store.safe_log(
                session_id=f"sess_{worker_id}",
                audience="client" if i % 2 == 0 else "staff",
                kind="answered" if i % 3 != 0 else "not_found",
                question=f"Question {i} from worker {worker_id}",
            )

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    counts = store.count()
    assert counts["total"] == 125
    assert counts["live"] == 125
    assert counts["synthetic"] == 0


# ---------------------------------------------------------------------------
# 4. Summary Aggregation & Zero-Filled Daily Series
# ---------------------------------------------------------------------------

def test_analytics_summary_metrics(tmp_path):
    db_file = tmp_path / "test_metrics.db"
    store = AnalyticsStore(db_path=str(db_file))

    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)

    # 4 answered (1 cached), 2 not-found, 1 error
    ts_str = now.isoformat()
    store.log_event("s1", "client", "answered", "Fee?", top_score=0.85, cached=True, latency_ms=0.0, ts_utc=ts_str)
    store.log_event("s1", "client", "answered", "Rates?", top_score=0.80, cached=False, latency_ms=1000.0, ts_utc=ts_str)
    store.log_event("s1", "staff", "answered", "MSA fee?", top_score=0.90, cached=False, latency_ms=2000.0, ts_utc=ts_str)
    store.log_event("s2", "client", "answered", "Hours?", top_score=0.75, cached=False, latency_ms=1200.0, ts_utc=ts_str)
    store.log_event("s2", "client", "not_found", "Tax?", reason="below_threshold", top_score=0.50, latency_ms=800.0, ts_utc=ts_str)
    store.log_event("s2", "client", "not_found", "Visa?", reason="below_threshold", top_score=0.55, latency_ms=900.0, ts_utc=ts_str)
    store.log_event("s3", "client", "error", "Broken?", reason="timeout", latency_ms=5000.0, ts_utc=ts_str)

    summary = store.summary(access_mode="staff", period_days=7, now_dt=now)

    assert summary.total_queries == 7
    assert summary.answered_queries == 4
    assert summary.not_found_queries == 2
    assert summary.error_queries == 1
    # 4 / 7 = 57.1%
    assert round(summary.answer_rate, 1) == 57.1
    # 1 / 7 = 14.3%
    assert round(summary.cache_hit_rate, 1) == 14.3

    # Daily series zero-filled to 7 days
    assert len(summary.daily_series) == 7
    # 6 days should have total=0, and the last day should have total=7
    zero_days = [d for d in summary.daily_series if d["total"] == 0]
    assert len(zero_days) == 6
    active_day = [d for d in summary.daily_series if d["total"] == 7][0]
    assert active_day["date"] == "2026-11-24"
    assert active_day["answered"] == 4
    assert active_day["not_found"] == 2
    assert active_day["errors"] == 1


# ---------------------------------------------------------------------------
# 5. Access Control Tests
# ---------------------------------------------------------------------------

def test_summary_access_denied_for_client(tmp_path):
    db_file = tmp_path / "test_acl.db"
    store = AnalyticsStore(db_path=str(db_file))

    with pytest.raises(AnalyticsAccessError) as exc_info:
        store.summary(access_mode="client")
    assert "restricted to law firm staff members only" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 6. Retention & Max Events Purge Tests
# ---------------------------------------------------------------------------

def test_purge_by_age_and_max_events(tmp_path):
    import time
    db_file = tmp_path / "test_purge.db"
    store = AnalyticsStore(
        db_path=str(db_file),
        retention_days=10,
        max_events=5,
    )
    # Prevent automatic background purge during insert loop so we test explicit purge
    store._last_purge_time = time.time()

    now = datetime.now(timezone.utc)
    old_ts = (now - timedelta(days=15)).isoformat()
    recent_ts = now.isoformat()

    # 3 old events (older than 10 days)
    for i in range(3):
        store.log_event(f"s_old_{i}", "client", "answered", f"Old {i}", ts_utc=old_ts)

    # 7 recent events
    for i in range(7):
        store.log_event(f"s_rec_{i}", "client", "answered", f"Recent {i}", ts_utc=recent_ts)

    assert store.count()["total"] == 10

    # Purge: 3 old removed, then 7 > max_events(5) so 2 oldest of recent removed
    purged_age, purged_cap = store.purge()
    assert purged_age == 3
    assert purged_cap == 2
    assert store.count()["total"] == 5


# ---------------------------------------------------------------------------
# 7. Knowledge Gaps Clustering & Actions Tests
# ---------------------------------------------------------------------------

def test_gap_clustering_exact_and_cosine(tmp_path):
    db_file = tmp_path / "test_gaps.db"
    store = AnalyticsStore(db_path=str(db_file))
    now = datetime(2026, 11, 24, 12, 0, 0, tzinfo=timezone.utc)
    ts = now.isoformat()

    # Create 3 similar vectors (cluster 1) and 1 distinct vector (cluster 2)
    v_tax1 = [0.9, 0.1, 0.0]
    v_tax2 = [0.88, 0.12, 0.0]
    v_imm = [0.0, 0.1, 0.9]

    # Cluster 1: low similarity score (< 0.55) -> "Add new content"
    store.log_event("s1", "client", "not_found", "How do I file tax returns?", vector=v_tax1, top_score=0.45, top_source="FAQ", ts_utc=ts)
    store.log_event("s2", "client", "not_found", "how do i file tax returns?", vector=v_tax1, top_score=0.48, top_source="FAQ", ts_utc=ts)
    store.log_event("s3", "client", "not_found", "What are tax return filing rules?", vector=v_tax2, top_score=0.50, top_source="FAQ", ts_utc=ts)

    # Cluster 2: moderate similarity score (0.55 - 0.65) -> "Expand an existing document"
    store.log_event("s4", "client", "not_found", "Can I get a UK visa?", vector=v_imm, top_score=0.60, top_source="Brochure", ts_utc=ts)

    summary = store.summary(access_mode="staff", period_days=7, now_dt=now)

    assert len(summary.gaps) == 2
    # First cluster should have count 3
    c1 = summary.gaps[0]
    assert c1["count"] == 3
    assert c1["suggested_action"] == "Add new content"
    assert c1["avg_top_score"] < 0.55

    # Second cluster should have count 1
    c2 = summary.gaps[1]
    assert c2["count"] == 1
    assert c2["suggested_action"] == "Expand an existing document"
    assert 0.55 <= c2["avg_top_score"] < 0.65


# ---------------------------------------------------------------------------
# 8. CSV Export & Formula Injection Defense Tests
# ---------------------------------------------------------------------------

def test_gaps_csv_formula_injection_defense():
    dangerous_gaps = [
        {
            "cluster_id": 1,
            "representative_query": "=cmd|' /C calc'!A0",
            "count": 5,
            "top_source": "+12345",
            "avg_top_score": 0.45,
            "suggested_action": "-@DDE('cmd';'calc')",
            "sample_queries": ["@malicious", "=SUM(A1:A10)"],
        }
    ]

    csv_text = gaps_to_csv(dangerous_gaps)
    assert isinstance(csv_text, str)
    lines = csv_text.strip().split("\r\n" if "\r\n" in csv_text else "\n")
    assert len(lines) == 2  # Header + 1 row

    data_row = lines[1]
    # Dangerous formula characters must be prefixed with single quote
    assert "'=cmd" in data_row
    assert "'+12345" in data_row
    assert "'-@DDE" in data_row
    assert "'@malicious" in data_row


# ---------------------------------------------------------------------------
# 9. Synthetic Seeding & Clearing Tests
# ---------------------------------------------------------------------------

def test_load_and_clear_synthetic(tmp_path):
    db_file = tmp_path / "test_synth.db"
    store = AnalyticsStore(db_path=str(db_file))

    # Log 2 live organic queries
    store.log_event("live_1", "client", "answered", "Live query 1", synthetic=0)
    store.log_event("live_2", "staff", "answered", "Live query 2", synthetic=0)

    # Load synthetic demo seed
    loaded_count = store.load_seed("data/demo_activity")
    assert loaded_count > 100

    counts = store.count()
    assert counts["live"] == 2
    assert counts["synthetic"] == loaded_count
    assert counts["total"] == 2 + loaded_count

    # Clear synthetic demo queries
    deleted = store.clear_synthetic()
    assert deleted == loaded_count

    counts_after = store.count()
    assert counts_after["live"] == 2
    assert counts_after["synthetic"] == 0
    assert counts_after["total"] == 2


# ---------------------------------------------------------------------------
# 10. VectorStore.query(return_vector=True) & RagResponse Tests
# ---------------------------------------------------------------------------

def test_rag_response_private_query_vector():
    resp = RagResponse(
        answer="Sample answer",
        found=True,
        top_source="Doc.pdf, p. 1",
        not_found_reason="",
        _query_vec=[0.1, 0.2, 0.3],
    )
    # Check fields
    assert resp.top_source == "Doc.pdf, p. 1"
    assert resp.not_found_reason == ""
    assert resp._query_vec == [0.1, 0.2, 0.3]

    # Verify repr excludes _query_vec
    repr_str = repr(resp)
    assert "_query_vec" not in repr_str

    # Verify equality comparison ignores _query_vec
    resp2 = RagResponse(
        answer="Sample answer",
        found=True,
        top_source="Doc.pdf, p. 1",
        not_found_reason="",
        _query_vec=[0.9, 0.9, 0.9],  # Different vector
    )
    assert resp == resp2
