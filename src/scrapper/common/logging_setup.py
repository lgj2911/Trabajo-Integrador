"""Logging configuration shared by the scrapers.

Entry points (CLI / Colab) call :func:`configure_logging` once with the log file
name that matches the municipality being scraped. Library modules only obtain a
logger via ``logging.getLogger(__name__)`` and never configure logging at import
time.
"""

from __future__ import annotations

import contextlib
import logging
import sys


def _build_handlers(log_file: str) -> list[logging.Handler]:
    """Build stdout + best-effort file handlers.

    Returns:
        A stream handler plus a file handler when the log file is writable.
    """
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    with contextlib.suppress(OSError):
        handlers.insert(0, logging.FileHandler(log_file, encoding="utf-8"))
    return handlers


def configure_logging(log_file: str) -> logging.Logger:
    """Configure the root logger for a scraper run.

    Returns:
        The package logger.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=_build_handlers(log_file),
    )
    return logging.getLogger("scrapper")
