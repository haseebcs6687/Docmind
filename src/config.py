"""Configuration and environment variable loader for DocMind."""

import os
from typing import Optional
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

# Optional model configurations (read from environment, no defaults guessed)
GEMINI_MODEL: Optional[str] = os.getenv("GEMINI_MODEL", "").strip() or None
GEMINI_EMBED_MODEL: Optional[str] = os.getenv("GEMINI_EMBED_MODEL", "").strip() or None


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
