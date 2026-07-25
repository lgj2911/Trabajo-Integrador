"""Convert a Rosario Plone HTML page into a PDF with weasyprint."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import aiohttp

from scrapper.common.config import HEADERS, HTTP_NOT_FOUND, HTTP_OK
from scrapper.common.urls import normalize_url

if TYPE_CHECKING:
    from pathlib import Path

log = logging.getLogger(__name__)


async def html_to_pdf_file(
    session: aiohttp.ClientSession,
    page_url: str,
    dest_path: Path,
    delay: float,
) -> bool | str:
    """Download the HTML of a Plone page and convert it to PDF with weasyprint.

    Returns:
        True on success, "PERMANENT" if the page is definitively unavailable or
        conversion fails irrecoverably, False for transient network errors.
    """
    url = normalize_url(page_url)
    if not url:
        return "PERMANENT"

    await asyncio.sleep(delay)
    try:
        async with session.get(
            url,
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=30),
            allow_redirects=True,
        ) as resp:
            if resp.status == HTTP_NOT_FOUND:
                return "PERMANENT"
            if resp.status != HTTP_OK:
                return False
            html = await resp.text(errors="replace")
            final_url = str(resp.url)
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        log.warning("Error fetching HTML from %s: %s", url, exc)
        return False

    # Run in an executor to avoid blocking the event loop.
    loop = asyncio.get_event_loop()
    try:

        def _convert() -> None:
            import weasyprint  # noqa: PLC0415 — lazy: requires GTK system libs

            dest_path.parent.mkdir(parents=True, exist_ok=True)
            weasyprint.HTML(string=html, base_url=final_url).write_pdf(str(dest_path))

        await loop.run_in_executor(None, _convert)
    except (OSError, ValueError) as exc:
        log.warning("weasyprint failed for %s: %s", url, exc)
        return "PERMANENT"
    else:
        return True
