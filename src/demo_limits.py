"""Daily quota budget guards and Pacific date tracking for DocMind demo mode."""

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

from src.config import (
    DEMO_DAILY_QUESTION_BUDGET,
    DEMO_DAILY_UPLOAD_EMBED_BUDGET,
    DEMO_MODE,
    DEMO_QUOTA_TZ,
)

logger = logging.getLogger(__name__)

DEFAULT_LIMITS_DB = str(Path(__file__).resolve().parent.parent / "data" / "demo_limits.db")
_DB_LOCK = threading.Lock()

BUDGET_EXCEEDED_MESSAGE = "Today's free demo capacity has been used up. Please come back tomorrow."
UPLOAD_BUDGET_EXCEEDED_MESSAGE = "Today's free demo upload capacity has been used up. Please come back tomorrow."


def get_current_pacific_date(tz_name: str = DEMO_QUOTA_TZ, now_dt: Optional[datetime] = None) -> str:
    """Return the current calendar date string (YYYY-MM-DD) in Google's quota timezone (default Pacific time)."""
    if now_dt is None:
        now_dt = datetime.now(timezone.utc)
    elif now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)

    try:
        tz = ZoneInfo(tz_name)
    except Exception as exc:
        logger.warning("Failed loading timezone %s (%s). Falling back to UTC.", tz_name, type(exc).__name__)
        tz = timezone.utc

    local_dt = now_dt.astimezone(tz)
    return local_dt.strftime("%Y-%m-%d")


def _init_db(db_path: str) -> None:
    """Initialize SQLite table for tracking daily usage counters."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path, timeout=10.0) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_counters (
                date_str TEXT PRIMARY KEY,
                question_count INTEGER DEFAULT 0,
                upload_embed_count INTEGER DEFAULT 0,
                updated_at TEXT
            );
            """
        )
        conn.commit()


def check_and_count_question(
    db_path: Optional[str] = None,
    tz_name: str = DEMO_QUOTA_TZ,
    now_dt: Optional[datetime] = None,
) -> Tuple[bool, str]:
    """Check whether daily question capacity is available in demo mode and increment counter if allowed.

    Returns:
        (allowed: bool, message: str)
    """
    if not DEMO_MODE:
        return True, ""

    db = db_path or DEFAULT_LIMITS_DB
    date_str = get_current_pacific_date(tz_name=tz_name, now_dt=now_dt)

    try:
        with _DB_LOCK:
            _init_db(db)
            with sqlite3.connect(db, timeout=10.0) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT question_count FROM daily_counters WHERE date_str = ?",
                    (date_str,),
                )
                row = cursor.fetchone()
                current_q = row[0] if row else 0

                if current_q >= DEMO_DAILY_QUESTION_BUDGET:
                    return False, BUDGET_EXCEEDED_MESSAGE

                now_iso = datetime.now(timezone.utc).isoformat()
                cursor.execute(
                    """
                    INSERT INTO daily_counters (date_str, question_count, upload_embed_count, updated_at)
                    VALUES (?, 1, 0, ?)
                    ON CONFLICT(date_str) DO UPDATE SET
                        question_count = question_count + 1,
                        updated_at = excluded.updated_at;
                    """,
                    (date_str, now_iso),
                )
                conn.commit()
                return True, ""
    except Exception as exc:
        logger.error("check_and_count_question failed with error class %s", type(exc).__name__)
        # Fail safe
        return True, ""


def check_and_count_upload_embed(
    estimated_requests: int = 1,
    db_path: Optional[str] = None,
    tz_name: str = DEMO_QUOTA_TZ,
    now_dt: Optional[datetime] = None,
) -> Tuple[bool, str]:
    """Check whether daily upload embedding request budget is available in demo mode and increment if allowed.

    Returns:
        (allowed: bool, message: str)
    """
    if not DEMO_MODE:
        return True, ""

    db = db_path or DEFAULT_LIMITS_DB
    date_str = get_current_pacific_date(tz_name=tz_name, now_dt=now_dt)

    try:
        with _DB_LOCK:
            _init_db(db)
            with sqlite3.connect(db, timeout=10.0) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT upload_embed_count FROM daily_counters WHERE date_str = ?",
                    (date_str,),
                )
                row = cursor.fetchone()
                current_u = row[0] if row else 0

                if current_u + estimated_requests > DEMO_DAILY_UPLOAD_EMBED_BUDGET:
                    return False, UPLOAD_BUDGET_EXCEEDED_MESSAGE

                now_iso = datetime.now(timezone.utc).isoformat()
                cursor.execute(
                    """
                    INSERT INTO daily_counters (date_str, question_count, upload_embed_count, updated_at)
                    VALUES (?, 0, ?, ?)
                    ON CONFLICT(date_str) DO UPDATE SET
                        upload_embed_count = upload_embed_count + excluded.upload_embed_count,
                        updated_at = excluded.updated_at;
                    """,
                    (date_str, estimated_requests, now_iso),
                )
                conn.commit()
                return True, ""
    except Exception as exc:
        logger.error("check_and_count_upload_embed failed with error class %s", type(exc).__name__)
        return True, ""


def get_daily_usage(
    db_path: Optional[str] = None,
    tz_name: str = DEMO_QUOTA_TZ,
    now_dt: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return dictionary of current daily usage and remaining budgets."""
    db = db_path or DEFAULT_LIMITS_DB
    date_str = get_current_pacific_date(tz_name=tz_name, now_dt=now_dt)

    q_count = 0
    u_count = 0
    try:
        with _DB_LOCK:
            _init_db(db)
            with sqlite3.connect(db, timeout=10.0) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT question_count, upload_embed_count FROM daily_counters WHERE date_str = ?",
                    (date_str,),
                )
                row = cursor.fetchone()
                if row:
                    q_count, u_count = row[0], row[1]
    except Exception as exc:
        logger.error("get_daily_usage failed with error class %s", type(exc).__name__)

    return {
        "date": date_str,
        "questions_used": q_count,
        "questions_budget": DEMO_DAILY_QUESTION_BUDGET,
        "questions_remaining": max(0, DEMO_DAILY_QUESTION_BUDGET - q_count),
        "upload_embed_used": u_count,
        "upload_embed_budget": DEMO_DAILY_UPLOAD_EMBED_BUDGET,
        "upload_embed_remaining": max(0, DEMO_DAILY_UPLOAD_EMBED_BUDGET - u_count),
    }
