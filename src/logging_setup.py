"""Logging configuration and external library noise suppression for DocMind."""

import logging


def configure_logging(level: int = logging.WARNING) -> None:
    """Configure root logging and suppress noisy third-party loggers."""
    logging.basicConfig(level=level, format="%(message)s")
    noisy_loggers = [
        "httpx",
        "httpx2",
        "httpcore",
        "httpcore2",
        "google",
        "google.auth",
        "google_genai",
        "google_genai.models",
        "google_genai._api_client",
        "google.genai",
        "google.genai.models",
        "google.genai.client",
        "chromadb",
        "urllib3",
    ]
    for name in noisy_loggers:
        log = logging.getLogger(name)
        log.setLevel(logging.WARNING)
        log.propagate = False

    # Dynamically suppress any existing logger matching transport or SDK prefixes
    for log_name in list(logging.root.manager.loggerDict.keys()):
        if any(log_name.lower().startswith(p) for p in ("httpx", "httpcore", "google", "chromadb", "urllib3")):
            logger_obj = logging.getLogger(log_name)
            logger_obj.setLevel(logging.WARNING)
            logger_obj.propagate = False
