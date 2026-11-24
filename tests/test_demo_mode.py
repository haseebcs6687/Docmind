"""Unit tests for Demo Mode, Zero-API Shared Index, Session Stores, and Isolation.

All tests run fully offline with 0 network calls.
"""

import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import List
from unittest import mock
import pytest

import chromadb
from src.config import (
    DEMO_DAILY_QUESTION_BUDGET,
    DEMO_DAILY_UPLOAD_EMBED_BUDGET,
    DEMO_MAX_CHUNKS_PER_SESSION,
    DEMO_MAX_TOTAL_SESSION_CHUNKS,
    DEMO_MAX_UPLOAD_FILES_PER_SESSION,
    DEMO_MAX_UPLOAD_MB,
    SCORE_THRESHOLD,
)
from src.demo_limits import (
    BUDGET_EXCEEDED_MESSAGE,
    UPLOAD_BUDGET_EXCEEDED_MESSAGE,
    check_and_count_question,
    check_and_count_upload_embed,
    get_daily_usage,
)
from src.loaders import DocUnit
from src.rag import ChatSession, RagResponse
from src.session_store import (
    CompositeStore,
    SessionDocStore,
    SessionQuotaExceededError,
    cleanup_expired,
    clear_all_sessions,
    get_global_session_chunks,
    get_session_store,
    resolve_name_collision,
)
from src.shared_index import compute_file_sha256, ensure_shared_index
from src.vectorstore import StoreReadOnlyError, VectorStore


@pytest.fixture(autouse=True)
def clean_sessions():
    """Ensure session stores are cleaned before and after each test."""
    clear_all_sessions()
    yield
    clear_all_sessions()


def test_readonly_store_refuses_mutating_methods(tmp_path):
    """Verify that a VectorStore with read_only=True raises StoreReadOnlyError on all write methods."""
    chroma_client = chromadb.PersistentClient(path=str(tmp_path))
    store = VectorStore(client=chroma_client, read_only=True)

    with pytest.raises(StoreReadOnlyError, match="read-only"):
        store.reset()

    with pytest.raises(StoreReadOnlyError, match="read-only"):
        store.delete_source("Test_Doc.pdf")

    with pytest.raises(StoreReadOnlyError, match="read-only"):
        store.set_source_metadata("Test_Doc.pdf", "client", "General")

    with pytest.raises(StoreReadOnlyError, match="read-only"):
        store.migrate_metadata_from_manifest()

    unit = DocUnit(source="test.txt", text="sample text", file_type="txt", page=1)
    with pytest.raises(StoreReadOnlyError, match="read-only"):
        store.index_units([unit], {"test.txt": "dummyhash"})


def test_ensure_shared_index_zero_api_calls(tmp_path):
    """Verify that ensure_shared_index populates an empty store with 97 chunks without calling embedder."""
    chroma_client = chromadb.PersistentClient(path=str(tmp_path))
    store = VectorStore(client=chroma_client, read_only=False)
    assert store.count() == 0

    def mock_embed_fn(*args, **kwargs):
        raise AssertionError("Embedding API was called during zero-API index import!")

    with mock.patch("src.shared_index.load_file", side_effect=mock_embed_fn):
        success = ensure_shared_index(store)

    assert success is True
    assert store.count() == 97

    # Verify all 8 documents exist
    sources = store.list_sources()
    assert len(sources) == 8

    # Verify client access: 4 docs / 52 chunks
    client_sources = store.list_sources(allowed_visibility={"client"})
    assert len(client_sources) == 4
    assert sum(s["chunk_count"] for s in client_sources) == 52


def test_stale_export_guard():
    """Verify that SHA-256 of all files in data/sample_docs match the export manifest."""
    manifest_path = Path("data/demo_index/index.json")
    assert manifest_path.exists(), "Export manifest data/demo_index/index.json must exist."

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    recorded_hashes = manifest.get("source_hashes", {})
    assert len(recorded_hashes) == 8

    sample_docs_dir = Path("data/sample_docs")
    for file_path in sample_docs_dir.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in (".pdf", ".docx", ".txt") and not file_path.name.startswith("."):
            real_hash = compute_file_sha256(file_path)
            assert file_path.name in recorded_hashes, f"Missing source {file_path.name} in export manifest"
            expected_hash = recorded_hashes[file_path.name]
            assert real_hash == expected_hash, f"Export is stale for {file_path.name}: expected {expected_hash}, got {real_hash}"


def test_session_isolation():
    """Verify that two browser sessions remain completely isolated in-memory."""
    store_a = get_session_store("session_alpha")
    store_b = get_session_store("session_beta")

    assert store_a.count() == 0
    assert store_b.count() == 0

    unit_a = DocUnit(
        source="Alpha_Private.txt",
        text="Alpha secret confidential retainer details PKR 999,000.",
        file_type="txt",
        page=1,
    )

    fake_embed = lambda texts, task: [[0.1] * 768 for _ in texts]

    rep = store_a.index_units(
        units=[unit_a],
        file_hash_by_source={"Alpha_Private.txt": "hash_a"},
        embed_fn=fake_embed,
    )
    assert rep["total_chunks_added"] >= 1
    assert store_a.count() >= 1

    # Session B must see nothing of Session A
    assert store_b.count() == 0
    assert len(store_b.list_sources()) == 0
    res_b = store_b.query_by_vector([0.1] * 768, k=5)
    assert len(res_b) == 0


def test_session_ttl_cleanup():
    """Verify that cleanup_expired deletes session stores that have exceeded the TTL."""
    store_old = get_session_store("sess_old")
    store_new = get_session_store("sess_new")

    # Set sess_old last_seen to 3 hours ago
    store_old.last_seen = time.time() - (3 * 3600)
    store_new.last_seen = time.time()

    cleaned = cleanup_expired(ttl_minutes=120)
    assert cleaned == 1

    # Old session is removed from registry
    # Creating with same id returns a fresh instance
    fresh = get_session_store("sess_old")
    assert fresh.created_at > store_old.created_at


def test_session_caps_enforcement():
    """Verify that session store enforces file count, chunk count, and file size limits."""
    sess = get_session_store("sess_caps")
    fake_embed = lambda texts, task: [[0.05] * 768 for _ in texts]

    # 1. File size limit
    big_unit = DocUnit(source="big.txt", text="huge", file_type="txt", page=1)
    with pytest.raises(SessionQuotaExceededError, match="maximum allowed size"):
        sess.index_units(
            units=[big_unit],
            file_hash_by_source={"big.txt": "h"},
            embed_fn=fake_embed,
            file_bytes_by_source={"big.txt": (DEMO_MAX_UPLOAD_MB + 1) * 1024 * 1024},
        )

    # 2. File count limit: DEMO_MAX_UPLOAD_FILES_PER_SESSION = 3
    for i in range(DEMO_MAX_UPLOAD_FILES_PER_SESSION):
        fn = f"file_{i}.txt"
        u = DocUnit(source=fn, text=f"Content for file {i}", file_type="txt", page=1)
        sess.index_units(units=[u], file_hash_by_source={fn: f"h_{i}"}, embed_fn=fake_embed)

    assert len(sess.uploaded_files) == DEMO_MAX_UPLOAD_FILES_PER_SESSION

    # 4th file should exceed quota
    overflow_unit = DocUnit(source="file_extra.txt", text="Extra", file_type="txt", page=1)
    with pytest.raises(SessionQuotaExceededError, match="Session file limit reached"):
        sess.index_units(
            units=[overflow_unit],
            file_hash_by_source={"file_extra.txt": "h_extra"},
            embed_fn=fake_embed,
        )


def test_name_collision_renaming():
    """Verify collision resolution correctly appends ' (yours)' and ' (yours N)'."""
    existing = {"Fee_Schedule_2026.pdf", "Fee_Schedule_2026 (yours).pdf"}
    assert resolve_name_collision("Other_Doc.pdf", existing) == "Other_Doc.pdf"
    assert resolve_name_collision("Fee_Schedule_2026.pdf", {"Fee_Schedule_2026.pdf"}) == "Fee_Schedule_2026 (yours).pdf"
    assert resolve_name_collision("Fee_Schedule_2026.pdf", existing) == "Fee_Schedule_2026 (yours 2).pdf"


def test_composite_store_query_merging_and_filtering():
    """Verify CompositeStore merges candidates by score and applies visibility filters."""
    mock_shared = mock.MagicMock(spec=VectorStore)
    mock_shared.count.return_value = 50
    mock_shared.get_fingerprint.return_value = "shared_fp"
    mock_shared.list_sources.return_value = [
        {"name": "Shared_1.pdf", "chunk_count": 50, "file_type": "pdf", "visibility": "staff", "practice_area": "General"}
    ]
    mock_shared.query_by_vector.return_value = [
        {"citation": "Shared_1.pdf, p. 1", "source": "Shared_1.pdf", "score": 0.82, "visibility": "staff", "practice_area": "General"}
    ]

    mock_sess = mock.MagicMock(spec=SessionDocStore)
    mock_sess.count.return_value = 2
    mock_sess.get_fingerprint.return_value = "sess_fp"
    mock_sess.list_sources.return_value = [
        {"name": "Private_Upload (yours).txt", "chunk_count": 2, "file_type": "txt", "visibility": "client", "practice_area": "General", "origin": "yours"}
    ]
    mock_sess.query_by_vector.return_value = [
        {"citation": "Private_Upload (yours).txt, p. 1", "source": "Private_Upload (yours).txt", "score": 0.91, "visibility": "client", "practice_area": "General", "origin": "yours"}
    ]

    composite = CompositeStore(shared=mock_shared, session=mock_sess)
    assert composite.count() == 52

    # Query without filter: Session chunk (0.91) before shared chunk (0.82)
    merged = composite.query_by_vector([0.1] * 768, k=5)
    assert len(merged) == 2
    assert merged[0]["score"] == 0.91
    assert merged[0]["origin"] == "yours"
    assert merged[1]["score"] == 0.82
    assert merged[1]["origin"] == "sample"


def test_composite_store_fingerprint_changes():
    """Verify that CompositeStore fingerprint changes when session store fingerprint changes."""
    mock_shared = mock.MagicMock(spec=VectorStore)
    mock_shared.get_fingerprint.return_value = "fixed_shared_hash"

    sess = get_session_store("sess_fp_test")
    composite = CompositeStore(shared=mock_shared, session=sess)

    fp1 = composite.get_fingerprint()

    # Add chunk to session
    unit = DocUnit(source="custom.txt", text="Custom policy text", file_type="txt", page=1)
    fake_embed = lambda texts, task: [[0.2] * 768 for _ in texts]
    sess.index_units([unit], {"custom.txt": "hash1"}, embed_fn=fake_embed)

    fp2 = composite.get_fingerprint()
    assert fp1 != fp2, "Composite fingerprint must change when session content changes"


def test_analytics_privacy_session_source_masked():
    """Verify that analytics logs mask session upload sources to '[uploaded document]'."""
    mock_analytics = mock.MagicMock()

    session = ChatSession(
        store=mock.MagicMock(),
        cooldown_seconds=0,
        max_questions=10,
        access_mode="staff",
        analytics=mock_analytics,
    )

    # Mock answer return with a session source
    fake_resp = RagResponse(
        answer="The test policy requires approval.",
        found=True,
        sources=[{
            "citation": "Custom_Policy (yours).txt, p. 1",
            "source": "Custom_Policy (yours).txt",
            "score": 0.88,
            "origin": "yours",
        }],
        top_score=0.88,
        top_source="Custom_Policy (yours).txt, p. 1",
        top_source_origin="yours",
    )

    with mock.patch("src.rag.answer", return_value=fake_resp):
        session.ask("What is the policy approval rule?")

    assert mock_analytics.safe_log.called
    kwargs = mock_analytics.safe_log.call_args[1]

    assert kwargs["top_source"] == "[uploaded document]"
    assert kwargs["cited_sources"] == ["[uploaded document]"]


def test_daily_budget_tracker_and_pacific_rollover(tmp_path):
    """Verify daily budget counters and Pacific timezone midnight rollover."""
    from datetime import datetime, timezone

    db_file = str(tmp_path / "test_limits.db")

    # Day 1: 2026-11-24 10:00:00 UTC (02:00 Pacific on 2026-11-24)
    dt_day1 = datetime(2026, 11, 24, 10, 0, 0, tzinfo=timezone.utc)

    with mock.patch("src.demo_limits.DEMO_MODE", True), \
         mock.patch("src.demo_limits.DEMO_DAILY_QUESTION_BUDGET", 2):

        allowed, msg = check_and_count_question(db_path=db_file, now_dt=dt_day1)
        assert allowed is True

        allowed, msg = check_and_count_question(db_path=db_file, now_dt=dt_day1)
        assert allowed is True

        # 3rd question exceeds budget
        allowed, msg = check_and_count_question(db_path=db_file, now_dt=dt_day1)
        assert allowed is False
        assert msg == BUDGET_EXCEEDED_MESSAGE

        # Day 2: 24 hours later (2026-11-25 10:00:00 UTC)
        dt_day2 = datetime(2026, 11, 25, 10, 0, 0, tzinfo=timezone.utc)
        allowed, msg = check_and_count_question(db_path=db_file, now_dt=dt_day2)
        assert allowed is True
        assert msg == ""


def test_ui_demo_mode_controls_and_banner():
    """Verify that AppTest in demo mode renders the disclaimer banner in sidebar."""
    from streamlit.testing.v1 import AppTest

    mock_shared = mock.MagicMock(spec=VectorStore)
    mock_shared.count.return_value = 8
    mock_shared.list_sources.return_value = [
        {"name": "Fee_Schedule_2026.pdf", "chunk_count": 8, "file_type": "pdf", "origin": "sample", "visibility": "staff"}
    ]
    mock_shared.get_fingerprint.return_value = "dummy_fp"

    app_path = str(Path(__file__).resolve().parent.parent / "app.py")

    with mock.patch("src.config.DEMO_MODE", True), \
         mock.patch("src.ui.state.DEMO_MODE", True), \
         mock.patch("app.DEMO_MODE", True), \
         mock.patch("src.ui.documents_page.DEMO_MODE", True), \
         mock.patch("src.ui.insights_page.DEMO_MODE", True), \
         mock.patch("src.ui.state.get_shared_store", return_value=mock_shared):

        at = AppTest.from_file(app_path, default_timeout=15)
        at.run()
        assert len(at.exception) == 0

        # Check demo banner in sidebar markdown
        sidebar_markdowns = [m.value for m in at.sidebar.markdown]
        banner_present = any("Public demo" in m and "fictional data" in m for m in sidebar_markdowns)
        assert banner_present, "Sidebar must render public demo disclaimer banner."

