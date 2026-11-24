"""Configuration and environment variable loader for DocMind."""

import os
from typing import Optional
from dotenv import load_dotenv
from src.logging_setup import configure_logging

# Load variables from .env file and silence noisy third-party loggers
load_dotenv()
configure_logging()

# Model configurations (read from environment, no defaults guessed)
GEMINI_MODEL: Optional[str] = os.getenv("GEMINI_MODEL", "").strip() or None
GEMINI_FALLBACK_MODEL: Optional[str] = os.getenv("GEMINI_FALLBACK_MODEL", "").strip() or None
GEMINI_EMBED_MODEL: Optional[str] = os.getenv("GEMINI_EMBED_MODEL", "").strip() or None

# Maximum upload file size in megabytes (default 20 MB)
MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "20"))

# Vector Store and Chunking settings
CHROMA_DIR: str = os.getenv("CHROMA_DIR", "chroma_db")
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "150"))
EMBED_BATCH_SIZE: int = int(os.getenv("EMBED_BATCH_SIZE", "20"))
EMBED_BATCH_SLEEP_SECONDS: float = float(os.getenv("EMBED_BATCH_SLEEP_SECONDS", "1.0"))

# RAG Pipeline, Client Timeout and Retry Settings
GEMINI_TIMEOUT_SECONDS: int = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "25"))
GEN_ANALYSIS_TIMEOUT_SECONDS: int = int(os.getenv("GEN_ANALYSIS_TIMEOUT_SECONDS", "45"))
TOP_K: int = int(os.getenv("TOP_K", "5"))
SCORE_THRESHOLD: float = float(os.getenv("SCORE_THRESHOLD", "0.65"))
MAX_CITATIONS: int = int(os.getenv("MAX_CITATIONS", "3"))
GEN_TEMPERATURE: float = float(os.getenv("GEN_TEMPERATURE", "0.1"))
GEN_PRIMARY_ATTEMPTS: int = int(os.getenv("GEN_PRIMARY_ATTEMPTS", "2"))
GEN_FALLBACK_ATTEMPTS: int = int(os.getenv("GEN_FALLBACK_ATTEMPTS", "2"))
GEN_MAX_RETRIES: int = int(os.getenv("GEN_MAX_RETRIES", "3"))
GEN_TOTAL_BUDGET_SECONDS: float = float(os.getenv("GEN_TOTAL_BUDGET_SECONDS", "60.0"))
GEN_THINKING_LEVEL: Optional[str] = os.getenv("GEN_THINKING_LEVEL")
HISTORY_TURNS: int = int(os.getenv("HISTORY_TURNS", "4"))
APP_TIMEZONE: str = os.getenv("APP_TIMEZONE", "Asia/Karachi")

# Analytics Configuration
ANALYTICS_ENABLED: bool = os.getenv("ANALYTICS_ENABLED", "true").lower() in ("true", "1", "yes")
ANALYTICS_DB_PATH: str = os.getenv("ANALYTICS_DB_PATH", "data/analytics.db")
ANALYTICS_RETENTION_DAYS: int = int(os.getenv("ANALYTICS_RETENTION_DAYS", "30"))
ANALYTICS_MAX_EVENTS: int = int(os.getenv("ANALYTICS_MAX_EVENTS", "5000"))
GAP_CLUSTER_COSINE: float = float(os.getenv("GAP_CLUSTER_COSINE", "0.80"))
GAP_JACCARD: float = float(os.getenv("GAP_JACCARD", "0.5"))

# Contract Analysis Configuration
MAX_ANALYSIS_CHARS: int = int(os.getenv("MAX_ANALYSIS_CHARS", "60000"))
MAX_ANALYSES_PER_SESSION: int = int(os.getenv("MAX_ANALYSES_PER_SESSION", "10"))
MIN_SECONDS_BETWEEN_ANALYSES: float = float(os.getenv("MIN_SECONDS_BETWEEN_ANALYSES", "5.0"))

# Client Reply Drafting Configuration
MAX_DRAFTS_PER_SESSION: int = int(os.getenv("MAX_DRAFTS_PER_SESSION", "15"))
MIN_SECONDS_BETWEEN_DRAFTS: float = float(os.getenv("MIN_SECONDS_BETWEEN_DRAFTS", "3.0"))

# Document Access Modes & Practice Areas
ACCESS_MODES = ("staff", "client")
PRACTICE_AREAS = (
    "General",
    "Billing & Fees",
    "Contracts",
    "Operations",
    "Compliance & Data",
    "Family Law",
    "Property",
    "Corporate",
)
DEFAULT_UPLOAD_VISIBILITY = "staff"

# Demo Quota and Session Limits
MIN_SECONDS_BETWEEN_QUESTIONS: float = float(os.getenv("MIN_SECONDS_BETWEEN_QUESTIONS", "3.0"))
MAX_QUESTIONS_PER_SESSION: int = int(os.getenv("MAX_QUESTIONS_PER_SESSION", "40"))
ANSWER_CACHE_TTL_SECONDS: int = int(os.getenv("ANSWER_CACHE_TTL_SECONDS", "1800"))
MAX_CHUNKS_PER_UPLOAD_BATCH: int = int(os.getenv("MAX_CHUNKS_PER_UPLOAD_BATCH", "300"))
MAX_TOTAL_CHUNKS: int = int(os.getenv("MAX_TOTAL_CHUNKS", "1500"))


def get_gemini_api_key() -> str:
    """Retrieve the Gemini API key from environment variables.

    Raises:
        ValueError: If GEMINI_API_KEY is missing or empty.
    """
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "GEMINI_API_KEY is missing or empty. "
            "Please add your Gemini API key to the .env file or environment variables."
        )
    return key


def __getattr__(name: str) -> str:
    """Expose GEMINI_API_KEY dynamically with validation on access."""
    if name == "GEMINI_API_KEY":
        return get_gemini_api_key()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
