"""Knowledge Insights & Analytics core engine for DocMind.

Stores anonymized, PII-redacted query telemetry in a local SQLite database (WAL mode).
Supports gap clustering (cosine / Jaccard), usage aggregation, retention purging,
synthetic demo activity seeding, CSV export with formula injection defense,
and strict role-based access control.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import numpy as np

from src.config import (
    ANALYTICS_DB_PATH,
    ANALYTICS_ENABLED,
    ANALYTICS_MAX_EVENTS,
    ANALYTICS_RETENTION_DAYS,
    GAP_CLUSTER_COSINE,
    GAP_JACCARD,
)

logger = logging.getLogger(__name__)


class AnalyticsAccessError(PermissionError):
    """Raised when unauthorized role attempts to access analytics data."""
    pass


# ---------------------------------------------------------------------------
# PII Redaction
# ---------------------------------------------------------------------------

_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
# Pakistani phone formats: +92 3xx xxxxxxx, +92-3xx-xxxxxxx, 03xxxxxxxxx, 042-xxxxxxx, etc.
_RE_PHONE_PK = re.compile(
    r"(?:\+92|0092|0)?[-.\s]?(?:3[0-9]{2}|4[0-2][0-9]|5[1-8][0-9]|9[1-9][0-9])[-.\s]?[0-9]{7}\b"
)
# Generic international numbers (+xx xxx xxxxxxx)
_RE_PHONE_INTL = re.compile(r"\+[1-9][0-9]{0,2}[-.\s]?[0-9]{2,4}[-.\s]?[0-9]{3,4}[-.\s]?[0-9]{3,4}\b")
# Pakistani CNIC: 5 digits - 7 digits - 1 digit (e.g. 35201-1234567-1)
_RE_CNIC = re.compile(r"\b[0-9]{5}-[0-9]{7}-[0-9]\b")
# 9 or more consecutive digit sequences (IDs, card numbers, accounts)
_RE_LONG_DIGITS = re.compile(r"\b[0-9]{9,}\b")


def redact_pii(text: str) -> str:
    """Redact emails, phone numbers, CNICs, and long ID numbers from text.

    Truncates question text to 300 characters max.
    """
    if not text:
        return ""

    s = text
    s = _RE_EMAIL.sub("[email]", s)
    s = _RE_CNIC.sub("[id]", s)
    s = _RE_PHONE_PK.sub("[phone]", s)
    s = _RE_PHONE_INTL.sub("[phone]", s)
    s = _RE_LONG_DIGITS.sub("[id]", s)

    # Normalize whitespace and truncate
    s = " ".join(s.split())
    if len(s) > 300:
        s = s[:300].rstrip() + "..."
    return s


# ---------------------------------------------------------------------------
# Vector Serialization Helpers (float16 BLOB)
# ---------------------------------------------------------------------------

def vector_to_blob(vec: Optional[Union[List[float], np.ndarray]]) -> Optional[bytes]:
    """Convert float vector to float16 binary BLOB."""
    if vec is None:
        return None
    arr = np.asarray(vec, dtype=np.float16)
    return arr.tobytes()


def blob_to_vector(blob: Optional[bytes]) -> Optional[np.ndarray]:
    """Convert float16 binary BLOB back to float32 NumPy vector."""
    if blob is None:
        return None
    return np.frombuffer(blob, dtype=np.float16).astype(np.float32)


# ---------------------------------------------------------------------------
# CSV Formula Injection Defense
# ---------------------------------------------------------------------------

def _sanitize_csv_cell(val: Any) -> str:
    """Prefix dangerous spreadsheet formula triggers (=, +, -, @, tab) with a single quote."""
    val_str = str(val) if val is not None else ""
    if val_str and val_str[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + val_str
    return val_str


def gaps_to_csv(gaps: List[Dict[str, Any]]) -> str:
    """Format clustered knowledge gaps as CSV with formula injection defense."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Cluster ID",
        "Representative Question",
        "Count",
        "Top Retrieved Source",
        "Avg Top Score",
        "Suggested Action",
        "Sample Questions",
    ])
    for g in gaps:
        samples_joined = " | ".join(g.get("sample_queries", []))
        writer.writerow([
            _sanitize_csv_cell(g.get("cluster_id", "")),
            _sanitize_csv_cell(g.get("representative_query", "")),
            _sanitize_csv_cell(g.get("count", 0)),
            _sanitize_csv_cell(g.get("top_source", "")),
            _sanitize_csv_cell(f"{g.get('avg_top_score', 0.0):.3f}"),
            _sanitize_csv_cell(g.get("suggested_action", "")),
            _sanitize_csv_cell(samples_joined),
        ])
    return output.getvalue()


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class InsightsSummary:
    """Aggregated insights data structure for UI visualization."""

    total_queries: int = 0
    answered_queries: int = 0
    not_found_queries: int = 0
    error_queries: int = 0
    answer_rate: float = 0.0
    cache_hit_rate: float = 0.0
    avg_latency_ms: float = 0.0
    daily_series: List[Dict[str, Any]] = field(default_factory=list)
    gaps: List[Dict[str, Any]] = field(default_factory=list)
    top_questions: List[Dict[str, Any]] = field(default_factory=list)
    doc_usage: List[Dict[str, Any]] = field(default_factory=list)
    unused_docs: List[str] = field(default_factory=list)
    has_synthetic: bool = False


# ---------------------------------------------------------------------------
# AnalyticsStore
# ---------------------------------------------------------------------------

class AnalyticsStore:
    """Thread-safe SQLite storage for DocMind telemetry and insights."""

    def __init__(
        self,
        db_path: str = ANALYTICS_DB_PATH,
        enabled: bool = ANALYTICS_ENABLED,
        retention_days: int = ANALYTICS_RETENTION_DAYS,
        max_events: int = ANALYTICS_MAX_EVENTS,
    ) -> None:
        self.db_path = db_path
        self.enabled = enabled
        self.retention_days = retention_days
        self.max_events = max_events
        self._write_lock = threading.Lock()
        self._last_purge_time = 0.0

        if self.enabled:
            self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create a new SQLite connection with foreign keys and WAL mode."""
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize database schema with WAL mode and indexes."""
        with self._write_lock:
            with self._get_connection() as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ts_utc TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        audience TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        question TEXT NOT NULL,
                        standalone TEXT NOT NULL,
                        top_source TEXT NOT NULL,
                        top_score REAL NOT NULL,
                        cited_sources TEXT NOT NULL,
                        cached INTEGER NOT NULL,
                        latency_ms REAL NOT NULL,
                        model_used TEXT NOT NULL,
                        synthetic INTEGER NOT NULL DEFAULT 0,
                        vec BLOB
                    );
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts_utc);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_events_audience ON events(audience);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_events_synthetic ON events(synthetic);")
                conn.commit()

    def log_event(
        self,
        session_id: str,
        audience: str,
        kind: str,
        question: str,
        reason: str = "",
        standalone: str = "",
        top_source: str = "",
        top_score: float = 0.0,
        cited_sources: Optional[List[str]] = None,
        cached: bool = False,
        latency_ms: float = 0.0,
        model_used: str = "",
        synthetic: int = 0,
        vector: Optional[Union[List[float], np.ndarray]] = None,
        ts_utc: Optional[str] = None,
    ) -> None:
        """Record an analytics event to SQLite.

        Privacy guarantee:
        - Questions and standalone queries are PII-redacted and truncated.
        - Embedding vector is stored ONLY for not_found events. Answered and error
          events store NULL in the vec column.
        - No answers, IP addresses, or document text are stored.
        """
        if not self.enabled:
            return

        redacted_q = redact_pii(question)
        redacted_standalone = redact_pii(standalone) if standalone else ""
        sources_json = json.dumps(cited_sources or [])
        cached_int = 1 if cached else 0
        now_ts = ts_utc or datetime.now(timezone.utc).isoformat()

        # Vector is ONLY stored for not_found queries (used for gap clustering)
        blob = vector_to_blob(vector) if (kind == "not_found" and vector is not None) else None

        with self._write_lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO events (
                        ts_utc, session_id, audience, kind, reason,
                        question, standalone, top_source, top_score,
                        cited_sources, cached, latency_ms, model_used,
                        synthetic, vec
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        now_ts,
                        session_id,
                        audience.lower(),
                        kind.lower(),
                        reason,
                        redacted_q,
                        redacted_standalone,
                        top_source or "",
                        float(top_score or 0.0),
                        sources_json,
                        cached_int,
                        float(latency_ms or 0.0),
                        model_used or "",
                        int(synthetic),
                        blob,
                    ),
                )
                conn.commit()

        # Throttled background purge
        self._maybe_purge()

    def safe_log(self, **kwargs: Any) -> None:
        """Safe wrapper around log_event that never raises exceptions."""
        try:
            self.log_event(**kwargs)
        except Exception as exc:
            logger.warning("Failed to record analytics event: %s", exc)

    def _maybe_purge(self) -> None:
        """Run purge at most once per hour."""
        now = datetime.now(timezone.utc).timestamp()
        if now - self._last_purge_time > 3600.0:
            self._last_purge_time = now
            try:
                self.purge()
            except Exception as exc:
                logger.warning("Background analytics purge failed: %s", exc)

    def purge(self) -> Tuple[int, int]:
        """Purge records exceeding retention days and cap table to max_events.

        Returns (purged_by_age, purged_by_cap).
        """
        if not self.enabled:
            return (0, 0)

        purged_age = 0
        purged_cap = 0
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat()

        with self._write_lock:
            with self._get_connection() as conn:
                # 1. Purge older than retention days
                cur = conn.execute("DELETE FROM events WHERE ts_utc < ?;", (cutoff,))
                purged_age = cur.rowcount

                # 2. Purge excess if count > max_events
                cur = conn.execute("SELECT count(*) FROM events;")
                total_rows = cur.fetchone()[0]
                if total_rows > self.max_events:
                    excess = total_rows - self.max_events
                    cur = conn.execute(
                        """
                        DELETE FROM events WHERE id IN (
                            SELECT id FROM events ORDER BY ts_utc ASC LIMIT ?
                        );
                        """,
                        (excess,),
                    )
                    purged_cap = cur.rowcount
                conn.commit()

        return (purged_age, purged_cap)

    def summary(
        self,
        access_mode: str,
        period_days: int = 14,
        audience: str = "all",
        known_sources: Optional[List[str]] = None,
        now_dt: Optional[datetime] = None,
    ) -> InsightsSummary:
        """Generate high-level aggregated insights for law firm staff."""
        if access_mode.lower() != "staff":
            raise AnalyticsAccessError(
                "Analytics and Knowledge Insights are restricted to law firm staff members only. "
                "Please switch to Staff mode in the sidebar."
            )

        if not self.enabled:
            return InsightsSummary()

        now = now_dt or datetime.now(timezone.utc)
        start_utc = (now - timedelta(days=period_days)).isoformat()

        query = "SELECT * FROM events WHERE ts_utc >= ?"
        params: List[Any] = [start_utc]

        if audience.lower() in ("client", "staff"):
            query += " AND audience = ?"
            params.append(audience.lower())

        query += " ORDER BY ts_utc ASC;"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        if not rows:
            # Build zero-filled daily series even when no events exist
            daily_series = []
            for d in range(period_days - 1, -1, -1):
                day_str = (now - timedelta(days=d)).strftime("%Y-%m-%d")
                daily_series.append({
                    "date": day_str,
                    "answered": 0,
                    "not_found": 0,
                    "errors": 0,
                    "total": 0,
                })
            return InsightsSummary(
                daily_series=daily_series,
                unused_docs=list(known_sources or []),
            )

        total_queries = len(rows)
        answered_queries = sum(1 for r in rows if r["kind"] == "answered")
        not_found_queries = sum(1 for r in rows if r["kind"] == "not_found")
        error_queries = sum(1 for r in rows if r["kind"] == "error")

        answer_rate = (answered_queries / total_queries * 100.0) if total_queries > 0 else 0.0
        cached_count = sum(1 for r in rows if r["cached"])
        cache_hit_rate = (cached_count / total_queries * 100.0) if total_queries > 0 else 0.0
        non_cached_rows = [r for r in rows if not r["cached"]]
        avg_latency_ms = (sum(r["latency_ms"] for r in non_cached_rows) / len(non_cached_rows)) if non_cached_rows else 0.0
        has_synthetic = any(bool(r["synthetic"]) for r in rows)

        # Zero-filled daily series
        daily_map: Dict[str, Dict[str, int]] = {}
        for d in range(period_days - 1, -1, -1):
            day_str = (now - timedelta(days=d)).strftime("%Y-%m-%d")
            daily_map[day_str] = {"answered": 0, "not_found": 0, "errors": 0, "total": 0}

        for r in rows:
            day_key = r["ts_utc"][:10]
            if day_key in daily_map:
                daily_map[day_key]["total"] += 1
                kind = r["kind"]
                if kind == "answered":
                    daily_map[day_key]["answered"] += 1
                elif kind == "not_found":
                    daily_map[day_key]["not_found"] += 1
                elif kind == "error":
                    daily_map[day_key]["errors"] += 1

        daily_series = [{"date": k, **v} for k, v in sorted(daily_map.items())]

        # Knowledge Gaps Clustering
        not_found_rows = [r for r in rows if r["kind"] == "not_found"]
        gaps = self._cluster_gaps(not_found_rows)

        # Most Asked Questions
        top_questions = self._aggregate_top_questions(rows)

        # Document Usage
        doc_usage, unused_docs = self._aggregate_doc_usage(rows, known_sources)

        return InsightsSummary(
            total_queries=total_queries,
            answered_queries=answered_queries,
            not_found_queries=not_found_queries,
            error_queries=error_queries,
            answer_rate=answer_rate,
            cache_hit_rate=cache_hit_rate,
            avg_latency_ms=avg_latency_ms,
            daily_series=daily_series,
            gaps=gaps,
            top_questions=top_questions,
            doc_usage=doc_usage,
            unused_docs=unused_docs,
            has_synthetic=has_synthetic,
        )

    def _cluster_gaps(self, rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
        """Cluster not_found events using exact text matches, cosine similarity, or Jaccard."""
        if not rows:
            return []

        # Parse items
        items = []
        for r in rows:
            vec = blob_to_vector(r["vec"])
            items.append({
                "question": r["question"],
                "norm_q": re.sub(r"[^\w\s]", "", r["question"].lower()).strip(),
                "top_source": r["top_source"],
                "top_score": r["top_score"],
                "vec": vec,
            })

        # Step 1: Initial grouping by normalized question
        norm_groups: Dict[str, List[Dict[str, Any]]] = {}
        for it in items:
            nq = it["norm_q"] or it["question"]
            norm_groups.setdefault(nq, []).append(it)

        # Convert groups to candidate clusters
        candidates: List[Dict[str, Any]] = []
        for nq, group in norm_groups.items():
            rep = max(group, key=lambda x: len(x["question"]))["question"]
            # Average vector if available
            vecs = [x["vec"] for x in group if x["vec"] is not None]
            avg_vec = np.mean(vecs, axis=0) if vecs else None
            if avg_vec is not None:
                norm = np.linalg.norm(avg_vec)
                if norm > 0:
                    avg_vec = avg_vec / norm

            top_src = max((x["top_source"] for x in group if x["top_source"]), default="")
            avg_score = sum(x["top_score"] for x in group) / len(group)
            candidates.append({
                "representative": rep,
                "items": group,
                "vec": avg_vec,
                "top_source": top_src,
                "avg_score": avg_score,
            })

        # Step 2: Merge clusters based on Cosine Similarity (>= GAP_CLUSTER_COSINE) or Jaccard
        merged: List[Dict[str, Any]] = []
        for cand in candidates:
            merged_into = False
            for existing in merged:
                sim = 0.0
                if cand["vec"] is not None and existing["vec"] is not None:
                    # Cosine similarity
                    sim = float(np.dot(cand["vec"], existing["vec"]))
                else:
                    # Token Jaccard fallback
                    t1 = set(cand["representative"].lower().split())
                    t2 = set(existing["representative"].lower().split())
                    if t1 and t2:
                        sim = len(t1 & t2) / len(t1 | t2)

                threshold = GAP_CLUSTER_COSINE if (cand["vec"] is not None and existing["vec"] is not None) else GAP_JACCARD
                if sim >= threshold:
                    # Merge cand into existing
                    existing["items"].extend(cand["items"])
                    # Recompute centroid
                    all_vecs = [x["vec"] for x in existing["items"] if x["vec"] is not None]
                    if all_vecs:
                        new_centroid = np.mean(all_vecs, axis=0)
                        n = np.linalg.norm(new_centroid)
                        existing["vec"] = new_centroid / n if n > 0 else new_centroid
                    existing["avg_score"] = sum(x["top_score"] for x in existing["items"]) / len(existing["items"])
                    if not existing["top_source"]:
                        existing["top_source"] = cand["top_source"]
                    merged_into = True
                    break

            if not merged_into:
                merged.append(cand)

        # Step 3: Format gap cluster summaries
        result_gaps = []
        for idx, cl in enumerate(sorted(merged, key=lambda c: len(c["items"]), reverse=True), start=1):
            count = len(cl["items"])
            avg_score = cl["avg_score"]
            top_source = cl["top_source"] or "None"
            action = "Add new content" if avg_score < 0.55 else "Expand an existing document"
            samples = list(dict.fromkeys(x["question"] for x in cl["items"]))[:5]

            result_gaps.append({
                "cluster_id": idx,
                "representative_query": cl["representative"],
                "count": count,
                "top_source": top_source,
                "avg_top_score": avg_score,
                "suggested_action": action,
                "sample_queries": samples,
            })

        return result_gaps

    def _aggregate_top_questions(self, rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
        """Aggregate top asked questions by frequency."""
        q_map: Dict[str, List[sqlite3.Row]] = {}
        for r in rows:
            norm = re.sub(r"[^\w\s]", "", r["question"].lower()).strip()
            q_map.setdefault(norm, []).append(r)

        top_list = []
        for norm, group in sorted(q_map.items(), key=lambda kv: len(kv[1]), reverse=True):
            rep = group[0]["question"]
            count = len(group)
            audiences = list({x["audience"] for x in group})
            aud_str = "All" if len(audiences) > 1 else audiences[0].capitalize()
            top_src = max((x["top_source"] for x in group if x["top_source"]), default="-")
            avg_sc = sum(x["top_score"] for x in group) / count
            top_list.append({
                "question": rep,
                "count": count,
                "audience": aud_str,
                "top_source": top_src,
                "avg_score": avg_sc,
            })
            if len(top_list) >= 10:
                break

        return top_list

    def _aggregate_doc_usage(
        self,
        rows: List[sqlite3.Row],
        known_sources: Optional[List[str]],
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Count document citations and retrieval frequencies."""
        citation_counts: Dict[str, int] = {}
        query_counts: Dict[str, int] = {}

        for r in rows:
            # Parse cited sources JSON
            try:
                cited = json.loads(r["cited_sources"])
            except Exception:
                cited = []

            seen_cited_docs: Set[str] = set()
            for c in cited:
                # e.g. "Fee_Schedule_2026.pdf, p. 1" -> doc name "Fee_Schedule_2026.pdf"
                doc_name = c.split(",")[0].strip()
                if doc_name:
                    seen_cited_docs.add(doc_name)
                    citation_counts[doc_name] = citation_counts.get(doc_name, 0) + 1

            # Top source
            top_src = r["top_source"]
            if top_src:
                doc_name = top_src.split(",")[0].strip()
                if doc_name:
                    query_counts[doc_name] = query_counts.get(doc_name, 0) + 1

        all_active_docs = set(citation_counts.keys()) | set(query_counts.keys())
        doc_usage = []
        for doc in all_active_docs:
            doc_usage.append({
                "source": doc,
                "citation_count": citation_counts.get(doc, 0),
                "query_count": query_counts.get(doc, 0),
            })

        doc_usage.sort(key=lambda x: (x["citation_count"], x["query_count"]), reverse=True)

        unused_docs = []
        if known_sources:
            for s in known_sources:
                if s not in all_active_docs:
                    unused_docs.append(s)

        return doc_usage, sorted(unused_docs)

    def load_seed(
        self,
        seed_dir: Union[str, Path] = "data/demo_activity",
        now: Optional[datetime] = None,
    ) -> int:
        """Deterministically load demo activity events from seed files.

        Generates ~160 realistic events distributed across the past 14 business days,
        between 9:00 and 18:00 PKT (4:00 - 13:00 UTC), ~70% client, ~80% answered.
        Sets synthetic = 1.
        """
        seed_path = Path(seed_dir)
        questions_file = seed_path / "seed_questions.json"
        vectors_file = seed_path / "seed_vectors.npz"

        if not questions_file.exists():
            raise FileNotFoundError(f"Seed questions file not found: {questions_file}")

        with open(questions_file, "r", encoding="utf-8") as f:
            seed_questions = json.load(f)

        vectors_npz = None
        if vectors_file.exists():
            vectors_npz = np.load(vectors_file)

        now_dt = now or datetime.now(timezone.utc)
        events_to_insert = []

        # Deterministic generation using a fixed pseudorandom seed
        import random
        rng = random.Random(42)

        # Distribute ~160 queries over 14 days
        # Weekdays have ~12-16 queries, weekends have ~2-4 queries
        total_days = 14
        for d in range(total_days - 1, -1, -1):
            day_date = (now_dt - timedelta(days=d)).date()
            is_weekend = day_date.weekday() >= 5
            daily_query_target = rng.randint(2, 4) if is_weekend else rng.randint(11, 15)

            for _ in range(daily_query_target):
                # Target audience: ~70% client, ~30% staff
                is_client = (rng.random() < 0.70)
                target_aud = "client" if is_client else "staff"
                aud_pool = [q for q in seed_questions if q.get("audience") == target_aud]
                if not aud_pool:
                    aud_pool = seed_questions

                # Target answer mix: ~80% answered, ~20% not-found
                is_answered = (rng.random() < 0.80)
                kind_pool = [q for q in aud_pool if q.get("kind") == ("answered" if is_answered else "not_found")]
                if not kind_pool:
                    kind_pool = aud_pool

                item = rng.choice(kind_pool)
                q_id = item["id"]
                vec_arr = vectors_npz[q_id] if (vectors_npz and q_id in vectors_npz) else None

                # Hour between 09:00 and 18:00 PKT (04:00 and 13:00 UTC)
                hour_utc = rng.randint(4, 12)
                min_utc = rng.randint(0, 59)
                sec_utc = rng.randint(0, 59)
                ts = datetime(
                    day_date.year, day_date.month, day_date.day,
                    hour_utc, min_utc, sec_utc, tzinfo=timezone.utc
                ).isoformat()

                session_id = f"demo-sess-{day_date.strftime('%Y%m%d')}-{rng.randint(100, 999)}"
                cached = (rng.random() < 0.15)
                latency = 0.0 if cached else round(rng.uniform(1500.0, 6000.0), 1)

                events_to_insert.append({
                    "ts_utc": ts,
                    "session_id": session_id,
                    "audience": item.get("audience", "client"),
                    "kind": item.get("kind", "answered"),
                    "reason": item.get("reason", ""),
                    "question": item["question"],
                    "standalone": item.get("standalone", ""),
                    "top_source": item.get("top_source", ""),
                    "top_score": float(item.get("top_score", 0.0)),
                    "cited_sources": item.get("cited_sources", []),
                    "cached": cached,
                    "latency_ms": latency,
                    "model_used": "gemini-3.5-flash-lite" if item.get("kind") == "answered" else "",
                    "synthetic": 1,
                    "vector": vec_arr,
                })

        # Insert all synthetic events
        inserted_count = 0
        with self._write_lock:
            with self._get_connection() as conn:
                for ev in events_to_insert:
                    blob = vector_to_blob(ev["vector"]) if (ev["kind"] == "not_found" and ev["vector"] is not None) else None
                    conn.execute(
                        """
                        INSERT INTO events (
                            ts_utc, session_id, audience, kind, reason,
                            question, standalone, top_source, top_score,
                            cited_sources, cached, latency_ms, model_used,
                            synthetic, vec
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?);
                        """,
                        (
                            ev["ts_utc"],
                            ev["session_id"],
                            ev["audience"],
                            ev["kind"],
                            ev["reason"],
                            redact_pii(ev["question"]),
                            redact_pii(ev["standalone"]) if ev["standalone"] else "",
                            ev["top_source"],
                            ev["top_score"],
                            json.dumps(ev["cited_sources"]),
                            1 if ev["cached"] else 0,
                            ev["latency_ms"],
                            ev["model_used"],
                            blob,
                        ),
                    )
                    inserted_count += 1
                conn.commit()

        logger.info("Loaded %d synthetic demo analytics events.", inserted_count)
        return inserted_count

    def clear_synthetic(self) -> int:
        """Delete all synthetic events (synthetic = 1)."""
        if not self.enabled:
            return 0
        with self._write_lock:
            with self._get_connection() as conn:
                cur = conn.execute("DELETE FROM events WHERE synthetic = 1;")
                deleted = cur.rowcount
                conn.commit()
        return deleted

    def clear_all(self) -> None:
        """Clear all events from database."""
        if not self.enabled:
            return
        with self._write_lock:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM events;")
                conn.commit()

    def count(self) -> Dict[str, int]:
        """Return event counts breakdown: total, live, synthetic."""
        if not self.enabled:
            return {"total": 0, "live": 0, "synthetic": 0}
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                SELECT
                    count(*),
                    sum(CASE WHEN synthetic = 0 THEN 1 ELSE 0 END),
                    sum(CASE WHEN synthetic = 1 THEN 1 ELSE 0 END)
                FROM events;
                """
            )
            row = cur.fetchone()
            total = row[0] or 0
            live = row[1] or 0
            synthetic = row[2] or 0
            return {"total": total, "live": live, "synthetic": synthetic}
