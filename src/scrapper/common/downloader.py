"""Shared async download engine.

Provides the retryable PDF download used by every scraper, plain-text saving,
and the per-run download context (session + concurrency semaphore).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import aiofiles
import aiohttp

from scrapper.common.config import HEADERS, HTTP_NOT_FOUND, HTTP_OK

if TYPE_CHECKING:
    from pathlib import Path

log = logging.getLogger(__name__)

_MAX_RETRIES = 3


@dataclass
class DownloadCtx:
    """Shared state passed to every per-task coroutine during a run."""

    session: aiohttp.ClientSession
    semaphore: asyncio.Semaphore
    delay: float
    checkpoint_file: Path | None = None
    manifest_file: Path | None = None


async def _fetch_pdf_bytes(
    session: aiohttp.ClientSession,
    pdf_url: str,
    attempt: int,
    *,
    not_found_permanent: bool,
) -> tuple[bool | str, bytes | None]:
    """Perform a single HTTP GET and validate the PDF response.

    Returns:
        (True, data) on success with valid PDF bytes,
        ("PERMANENT", None) for a definitively bad response,
        (False, None) for a 404 when *not_found_permanent* is False,
        ("RETRY", None) on a retryable HTTP error.
    """
    async with session.get(
        pdf_url,
        headers={**HEADERS, "Accept": "application/pdf,*/*"},
        timeout=aiohttp.ClientTimeout(total=90),
        allow_redirects=True,
    ) as resp:
        if resp.status == HTTP_NOT_FOUND:
            log.warning("404 (document not available): %s", pdf_url)
            return ("PERMANENT" if not_found_permanent else False), None
        if resp.status != HTTP_OK:
            log.warning("HTTP %d on attempt %d/%d: %s", resp.status, attempt, _MAX_RETRIES, pdf_url)
            return "RETRY", None

        data = await resp.read()

        if not data or b"%PDF" not in data[:10]:
            ct = resp.headers.get("Content-Type", "")
            log.warning(
                "No valid PDF (Content-Type: %s, bytes: %d) — will be skipped: %s",
                ct,
                len(data),
                pdf_url,
            )
            return "PERMANENT", None

        return True, data


async def download_pdf(
    session: aiohttp.ClientSession,
    pdf_url: str,
    dest: Path,
    delay: float,
    *,
    not_found_permanent: bool = True,
) -> bool | str:
    """Download a PDF from *pdf_url* and write it to *dest*.

    Args:
        session: Shared aiohttp session.
        pdf_url: Direct URL of the PDF to download.
        dest: Destination path to write the file to.
        delay: Seconds to wait before the request (politeness throttle).
        not_found_permanent: When True a 404 is treated as a permanent failure
            (added to the checkpoint as SKIP); when False it is treated as a
            transient failure that is retried on the next run.

    Returns:
        True on success, "PERMANENT" for definitively bad responses, or False
        for transient failures that should be retried next run.
    """
    await asyncio.sleep(delay)
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            result, data = await _fetch_pdf_bytes(
                session, pdf_url, attempt, not_found_permanent=not_found_permanent
            )
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.warning("Error on attempt %d/%d (%s): %s", attempt, _MAX_RETRIES, pdf_url, exc)
            await asyncio.sleep(2**attempt)
            continue

        if result == "RETRY":
            await asyncio.sleep(2**attempt)
            continue
        if result is not True:
            return result  # False or "PERMANENT"

        assert data is not None
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(dest, "wb") as f:
            await f.write(data)
        return True

    log.error("Permanent network failure (will retry next run): %s", pdf_url)
    return False  # transient: do not add to checkpoint


async def save_text(text: str, dest: Path) -> None:
    """Write extracted plain text to *dest*."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(dest, "w", encoding="utf-8") as f:
        await f.write(text)
