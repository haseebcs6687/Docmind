"""Logging configuration and external library noise suppression for DocMind."""

import logging


def configure_logging(level: int = logging.WARNING) -> None:
    """Configure root logging and suppress noisy third-party loggers."""
    logging.basicConfig(level=level, format="%(message)s")
    for name in (
        "httpx",
        "httpcore",
        "google_genai",
        "google.genai",
        "google.genai.models",
        "google.genai.client",
        "chromadb",
        "urllib3",
    ):
        log = logging.getLogger(name)
        log.setLevel(logging.WARNING)
        log.propagate = False
