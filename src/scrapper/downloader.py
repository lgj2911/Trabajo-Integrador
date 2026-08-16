"""Backward-compatible facade for the Rosario downloader.

The implementation now lives in :mod:`scrapper.rosario` (with shared code in
:mod:`scrapper.common`). This module re-exports the public API so existing
imports (``from scrapper.downloader import ...``) keep working, and exposes the
historical ``run`` / ``run_colab`` / ``main`` entry points.

Preferred invocation for new code:

    python -m scrapper rosario --output ./downloads --concurrency 5 --delay 0.5
"""

from __future__ import annotations

import sys

from scrapper.common.checkpoint import (
    SKIP_PREFIX,
    is_pending,
    load_checkpoint,
    save_checkpoint,
)
from scrapper.common.downloader import download_pdf as download_file
from scrapper.common.urls import normalize_url
from scrapper.rosario.config import BASE_URL, CSV_CONFIG, SCRAPPER_DIR
from scrapper.rosario.extract import extract_pdf_url_from_html
from scrapper.rosario.htmlpdf import html_to_pdf_file
from scrapper.rosario.pipeline import run, run_colab
from scrapper.rosario.resolve import build_normativa_pdf_url, resolve_pdf_url
from scrapper.rosario.tasks import build_task_list, expand_boletin_tasks, sanitize

__all__ = [
    "BASE_URL",
    "CSV_CONFIG",
    "SCRAPPER_DIR",
    "SKIP_PREFIX",
    "build_normativa_pdf_url",
    "build_task_list",
    "download_file",
    "expand_boletin_tasks",
    "extract_pdf_url_from_html",
    "html_to_pdf_file",
    "is_pending",
    "load_checkpoint",
    "main",
    "normalize_url",
    "resolve_pdf_url",
    "run",
    "run_colab",
    "sanitize",
    "save_checkpoint",
]


def main() -> None:
    """Run the Rosario scraper through the unified CLI."""
    from scrapper.cli import main as cli_main  # noqa: PLC0415

    cli_main(["rosario", *sys.argv[1:]])


if __name__ == "__main__":
    main()
