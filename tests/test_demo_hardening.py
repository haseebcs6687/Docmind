"""Unit tests for Step 17: Public Demo Hardening, Multi-session Insights Privacy, and Deployment Safety.

All tests run strictly offline with 0 network calls.
"""

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sqlite3
import tempfile
from unittest import mock
import pytest

from src.config import (
    DEMO_DAILY_GENERATION_BUDGET,
    DEMO_DAILY_EMBED_BUDGET,
    DEMO_REAL_EVENT_RETENTION_HOURS,
    check_storage_writable,
)
from src.analytics import AnalyticsStore, ensure_demo_activity, gaps_to_csv
from src.demo_limits import (
    BUDGET_EXCEEDED_MESSAGE,
    check_and_count_generation,
    check_and_count_embed,
    is_generation_budget_near_limit,
    get_daily_usage,
    get_current_pacific_date,
)
from src.gemini_client import (
    GenerationError,
    ErrorCategory,
    call_with_retry_and_fallback,
)
from src.vectorstore import EmbeddingError, embed_texts
from scripts.deploy_hf import scan_file_for_secrets, is_ignored, load_dockerignore_rules


# ---------------------------------------------------------------------------
# B1. Insights Multi-Session Privacy Isolation & Retention Purge
# ---------------------------------------------------------------------------

def test_insights_session_isolation_in_demo_mode(tmp_path):
    """Verify that in demo mode, visitors see only synthetic events + their own session queries."""
    db_path = str(tmp_path / "analytics_test.db")
    store = AnalyticsStore(db_path=db_path)

    # 1. Insert synthetic events
    store.log_event(
        session_id="synth-sess-1",
        audience="client",
        kind="answered",
        question="What are office hours?",
        synthetic=1,
    )
    store.log_event(
        session_id="synth-sess-2",
        audience="client",
        kind="not_found",
        question="Do you have parking?",
        synthetic=1,
    )

    # 2. Insert Session A events
    store.log_event(
        session_id="session_A",
        audience="client",
        kind="answered",
        question="Session A private query about fees",
        synthetic=0,
    )
    store.log_event(
        session_id="session_A",
        audience="client",
        kind="not_found",
        question="Session A private query not found",
        synthetic=0,
    )

    # 3. Insert Session B events
    store.log_event(
        session_id="session_B",
        audience="client",
        kind="answered",
        question="Session B secret tax question",
        synthetic=0,
    )

    with mock.patch("src.analytics.DEMO_MODE", True):
        # Session A view:
        summary_a = store.summary(access_mode="staff", session_id="session_A")
        assert summary_a.total_queries == 4  # 2 synthetic + 2 session A
        top_qs_a = [q["question"] for q in summary_a.top_questions]
        assert any("Session A" in q for q in top_qs_a)
        assert not any("Session B" in q for q in top_qs_a)

        # Gap list for Session A contains only synthetic not_found + Session A not_found
        gaps_a = summary_a.gaps
        csv_a = gaps_to_csv(gaps_a)
        assert "Session B" not in csv_a

        # Session B view:
        summary_b = store.summary(access_mode="staff", session_id="session_B")
        assert summary_b.total_queries == 3  # 2 synthetic + 1 session B
        top_qs_b = [q["question"] for q in summary_b.top_questions]
        assert any("Session B" in q for q in top_qs_b)
        assert not any("Session A" in q for q in top_qs_b)

        # Anonymous view without session_id (synthetic only):
        summary_anon = store.summary(access_mode="staff", session_id=None)
        assert summary_anon.total_queries == 2
        top_qs_anon = [q["question"] for q in summary_anon.top_questions]
        assert not any("Session A" in q for q in top_qs_anon)
        assert not any("Session B" in q for q in top_qs_anon)

        # Counters isolation
        count_a = store.count(session_id="session_A")
        assert count_a["total"] == 4
        assert count_a["live"] == 2
        assert count_a["synthetic"] == 2

        count_b = store.count(session_id="session_B")
        assert count_b["total"] == 3
        assert count_b["live"] == 1
        assert count_b["synthetic"] == 2


def test_purge_old_real_events(tmp_path):
    """Verify that real non-synthetic events older than 24 hours are purged while synthetic remain."""
    db_path = str(tmp_path / "analytics_purge.db")
    store = AnalyticsStore(db_path=db_path)

    now = datetime.now(timezone.utc)
    old_time = (now - timedelta(hours=25)).isoformat()
    recent_time = (now - timedelta(hours=2)).isoformat()

    # Synthetic event (even if old, must NOT be purged)
    store.log_event(
        session_id="synth",
        audience="client",
        kind="answered",
        question="Old synthetic question",
        synthetic=1,
        ts_utc=old_time,
    )
    # Old real event (should be purged)
    store.log_event(
        session_id="real_old",
        audience="client",
        kind="answered",
        question="Old real question",
        synthetic=0,
        ts_utc=old_time,
    )
    # Recent real event (should be kept)
    store.log_event(
        session_id="real_recent",
        audience="client",
        kind="answered",
        question="Recent real question",
        synthetic=0,
        ts_utc=recent_time,
    )

    deleted = store.purge_old_real_events(max_age_hours=24, now_dt=now)
    assert deleted == 1

    counts = store.count()
    assert counts["synthetic"] == 1
    assert counts["live"] == 1
    assert counts["total"] == 2


# ---------------------------------------------------------------------------
# B2. Cold Start Demo Activity Seeding
# ---------------------------------------------------------------------------

def test_ensure_demo_activity_idempotency(tmp_path):
    """Verify ensure_demo_activity seeds activity once and is idempotent with 0 duplicate rows."""
    db_path = str(tmp_path / "analytics_seed.db")
    store = AnalyticsStore(db_path=db_path)
    assert store.count()["synthetic"] == 0

    # First run populates data
    seeded = ensure_demo_activity(store, seed_dir="data/demo_activity")
    assert seeded is True
    first_count = store.count()["synthetic"]
    assert first_count > 50

    # Second run is a no-op (idempotent, 0 new rows)
    seeded_again = ensure_demo_activity(store, seed_dir="data/demo_activity")
    assert seeded_again is False
    assert store.count()["synthetic"] == first_count


# ---------------------------------------------------------------------------
# B3. Global Generation and Embed Budget Protection
# ---------------------------------------------------------------------------

def test_daily_generation_budget_exhaustion(tmp_path):
    """Verify that exceeding daily generation budget blocks requests with friendly message."""
    db_path = str(tmp_path / "limits_test.db")

    with mock.patch("src.demo_limits.DEMO_MODE", True), \
         mock.patch("src.demo_limits.DEMO_DAILY_GENERATION_BUDGET", 5):

        for i in range(5):
            allowed, msg = check_and_count_generation(db_path=db_path)
            assert allowed is True
            assert msg == ""

        # 6th request should be blocked
        allowed, msg = check_and_count_generation(db_path=db_path)
        assert allowed is False
        assert msg == BUDGET_EXCEEDED_MESSAGE

        usage = get_daily_usage(db_path=db_path)
        assert usage["generation_used"] == 5
        assert usage["generation_remaining"] == 0


def test_generation_layer_raises_on_exhausted_budget(tmp_path):
    """Verify call_with_retry_and_fallback raises GenerationError when generation budget is exhausted."""
    db_path = str(tmp_path / "limits_layer.db")

    with mock.patch("src.gemini_client.DEMO_MODE", True), \
         mock.patch("src.demo_limits.DEMO_MODE", True), \
         mock.patch("src.demo_limits.DEFAULT_LIMITS_DB", db_path), \
         mock.patch("src.demo_limits.DEMO_LIMITS_DB_PATH", db_path), \
         mock.patch("src.demo_limits.DEMO_DAILY_GENERATION_BUDGET", 2):

        mock_call = mock.MagicMock(return_value="Output")

        # Call 1 & 2 succeed
        call_with_retry_and_fallback(mock_call, primary_model="fake-model")
        call_with_retry_and_fallback(mock_call, primary_model="fake-model")
        assert mock_call.call_count == 2

        # Call 3 is blocked before invoking the model callable (0 API calls)
        with pytest.raises(GenerationError) as exc_info:
            call_with_retry_and_fallback(mock_call, primary_model="fake-model")

        assert exc_info.value.category == ErrorCategory.QUOTA_DAILY
        assert "Today's free demo capacity has been used up" in str(exc_info.value)
        # Mock call count must NOT have increased!
        assert mock_call.call_count == 2


def test_soft_notice_at_85_percent_budget(tmp_path):
    """Verify is_generation_budget_near_limit detects 85%+ threshold."""
    db_path = str(tmp_path / "limits_soft.db")
    test_dt = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    date_str = get_current_pacific_date(now_dt=test_dt)

    with mock.patch("src.demo_limits.DEMO_MODE", True), \
         mock.patch("src.demo_limits.DEMO_DAILY_GENERATION_BUDGET", 100):

        # At 50% -> no warning
        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS daily_counters (date_str TEXT PRIMARY KEY, generation_count INTEGER, updated_at TEXT)")
            conn.execute("INSERT INTO daily_counters (date_str, generation_count) VALUES (?, 50)", (date_str,))

        is_near, _ = is_generation_budget_near_limit(db_path=db_path, now_dt=test_dt)
        assert is_near is False

        # At 86% -> soft warning triggered
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE daily_counters SET generation_count = 86 WHERE date_str = ?", (date_str,))

        is_near, notice = is_generation_budget_near_limit(db_path=db_path, now_dt=test_dt)
        assert is_near is True
        assert "High demo traffic" in notice


def test_embed_budget_exhaustion(tmp_path):
    """Verify that daily embed budget is enforced and blocks embed_texts calls."""
    db_path = str(tmp_path / "limits_embed.db")

    with mock.patch("src.demo_limits.DEMO_MODE", True), \
         mock.patch("src.demo_limits.DEMO_DAILY_EMBED_BUDGET", 3):

        # Embed batch 1 & 2
        allowed, _ = check_and_count_embed(request_count=2, db_path=db_path)
        assert allowed is True

        # Request exceeding remaining (3 - 2 = 1 left, asking for 2)
        allowed, msg = check_and_count_embed(request_count=2, db_path=db_path)
        assert allowed is False
        assert msg == BUDGET_EXCEEDED_MESSAGE


# ---------------------------------------------------------------------------
# B4. Storage Paths and Writable Check
# ---------------------------------------------------------------------------

def test_check_storage_writable_healthy(tmp_path):
    """Verify check_storage_writable returns True on accessible directories."""
    with mock.patch("src.config.CHROMA_DIR", str(tmp_path / "chroma")), \
         mock.patch("src.config.ANALYTICS_DB_PATH", str(tmp_path / "data" / "analytics.db")), \
         mock.patch("src.config.DEMO_LIMITS_DB_PATH", str(tmp_path / "data" / "demo_limits.db")):
        is_ok, failed_path = check_storage_writable()
        assert is_ok is True
        assert failed_path is None


def test_check_storage_writable_failure(tmp_path):
    """Verify check_storage_writable detects unwritable directory."""
    with mock.patch("pathlib.Path.touch", side_effect=PermissionError("Read-only file system")):
        is_ok, failed_path = check_storage_writable()
        assert is_ok is False
        assert failed_path is not None


# ---------------------------------------------------------------------------
# C. Deployment Script & Secret Scanner
# ---------------------------------------------------------------------------

def test_secret_scanner_catches_planted_keys(tmp_path):
    """Verify pre-flight secret scanner catches Google API keys, HF tokens, and real-looking key assignments."""
    clean_file = tmp_path / "clean.py"
    clean_file.write_text("print('Clean code without secrets')", encoding="utf-8")

    # Assemble test strings from parts to prevent false positives during static repo greps
    fake_aiza = "AI" + "za" + "Sy" + ("A" * 33)
    fake_hf = "hf" + "_" + ("B" * 30)
    fake_gemini = "GEMINI" + "_API_KEY=kL9pQ2mZ5rT8vX1wY4bN7cD3eF6gH0jS"

    planted_key = tmp_path / "planted_key.py"
    planted_key.write_text(f"API_KEY = '{fake_aiza}'\n", encoding="utf-8")

    planted_hf = tmp_path / "planted_hf.py"
    planted_hf.write_text(f"TOKEN = '{fake_hf}'\n", encoding="utf-8")

    planted_env_assignment = tmp_path / "planted_assign.txt"
    planted_env_assignment.write_text(f"{fake_gemini}\n", encoding="utf-8")

    # Scanner results
    assert scan_file_for_secrets(str(clean_file)) == []

    key_findings = scan_file_for_secrets(str(planted_key))
    assert len(key_findings) > 0
    assert "Google Gemini API Key" in key_findings[0][0]
    assert key_findings[0][1].startswith(fake_aiza[:4])

    hf_findings = scan_file_for_secrets(str(planted_hf))
    assert len(hf_findings) > 0
    assert "Hugging Face Access Token" in hf_findings[0][0]
    assert hf_findings[0][1].startswith(fake_hf[:4])

    assign_findings = scan_file_for_secrets(str(planted_env_assignment))
    assert len(assign_findings) > 0
    assert "Prohibited Secret Assignment" in assign_findings[0][0]
    assert assign_findings[0][1].startswith("kL9p")


def test_secret_scanner_ignores_placeholders_and_doc_lines():
    """Verify placeholders, backticks, empty values, and documentation lines are not flagged."""
    doc_lines = [
        "GEMINI_API_KEY=",
        "GEMINI_API_KEY=`",
        "GEMINI_API_KEY=<your key>",
        "GEMINI_API_KEY=your_actual_gemini_api_key_here",
        'GEMINI_API_KEY="your_key_here"',
        'HF_TOKEN="hf_your_write_token_here"',
        "GEMINI_API_KEY=placeholder_token_for_docs",
        "GEMINI_API_KEY=dummy_value_string_12345",
        "GEMINI_API_KEY=example_gemini_key_reference",
    ]
    for line in doc_lines:
        findings = scan_file_for_secrets(line) if Path(line).exists() else []
        from scripts.deploy_hf import scan_content_for_secrets
        content_findings = scan_content_for_secrets(line)
        assert content_findings == [], f"Line wrongly flagged: {line} -> {content_findings}"


def test_secret_scanner_clean_on_repo_files():
    """Verify that real repository files that previously triggered scanner are now 100% clean."""
    for repo_file in ["docs/DEPLOY.md", "docs/PROGRESS.md", "scripts/deploy_hf.py"]:
        findings = scan_file_for_secrets(repo_file)
        assert findings == [], f"Unexpected secret scanner hit in {repo_file}: {findings}"


def test_dockerignore_rules_exclude_sensitive_files():
    """Verify .dockerignore rules exclude .env, .git, .venv, chroma_db, databases, and dev outputs."""
    rules = load_dockerignore_rules()
    assert is_ignored(".env", rules) is True
    assert is_ignored(".env.production", rules) is True
    assert is_ignored(".git/config", rules) is True
    assert is_ignored(".venv/bin/python", rules) is True
    assert is_ignored("tests/test_demo_mode.py", rules) is True
    assert is_ignored("data/analytics.db", rules) is True
    assert is_ignored("data/demo_limits.db", rules) is True
    assert is_ignored("chroma_db/chroma.sqlite3", rules) is True
    assert is_ignored("eval/results/answers.md", rules) is True
    assert is_ignored("eval/results/latest.json", rules) is True
    assert is_ignored("scripts/generate_sample_docs.py", rules) is True
    assert is_ignored("scripts/verify_fresh_clone.py", rules) is True

    # Application runtime files must NOT be ignored
    assert is_ignored("app.py", rules) is False
    assert is_ignored("src/rag.py", rules) is False
    assert is_ignored("data/sample_docs/Fee_Schedule_2026.pdf", rules) is False
    assert is_ignored("data/demo_index/index.json", rules) is False
    assert is_ignored("data/demo_activity/seed_questions.json", rules) is False
    assert is_ignored("requirements.txt", rules) is False
