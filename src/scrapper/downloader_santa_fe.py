"""Backward-compatible facade for the Santa Fe downloader.

The implementation now lives in :mod:`scrapper.santafe` (with shared code in
:mod:`scrapper.common`). This module re-exports the public API so existing
imports (``from scrapper.downloader_santa_fe import ...``) keep working, and
exposes the historical ``run`` / ``run_colab`` / ``main`` entry points.

Preferred invocation for new code:

    python -m scrapper santafe --output ./downloads_santa_fe --concurrency 5
"""

from __future__ import annotations

import sys

from scrapper.common.checkpoint import (
    SKIP_PREFIX,
    is_pending,
    load_checkpoint,
    save_checkpoint,
)
from scrapper.common.downloader import download_pdf, save_text
from scrapper.santafe.config import ALL_COLLECTIONS, BASE_URL, SITEMAP_INDEX_URL
from scrapper.santafe.extract import extract_body_text, extract_wp_pdf_url
from scrapper.santafe.pipeline import run, run_colab
from scrapper.santafe.sitemap import enumerate_all_urls, fetch_sitemap_urls
from scrapper.santafe.tasks import build_task_list

__all__ = [
    "ALL_COLLECTIONS",
    "BASE_URL",
    "SITEMAP_INDEX_URL",
    "SKIP_PREFIX",
    "build_task_list",
    "download_pdf",
    "enumerate_all_urls",
    "extract_body_text",
    "extract_wp_pdf_url",
    "fetch_sitemap_urls",
    "is_pending",
    "load_checkpoint",
    "main",
    "run",
    "run_colab",
    "save_checkpoint",
    "save_text",
]


def main() -> None:
    """Run the Santa Fe scraper through the unified CLI."""
    from scrapper.cli import main as cli_main  # noqa: PLC0415

    cli_main(["santafe", *sys.argv[1:]])


if __name__ == "__main__":
    main()
