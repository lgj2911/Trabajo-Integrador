"""Resolve a Rosario page URL into a direct PDF download URL."""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import parse_qs, urlparse

import aiohttp

from scrapper.common.config import HEADERS, HTTP_NOT_FOUND, HTTP_OK
from scrapper.common.urls import normalize_url
from scrapper.rosario.config import BASE_URL
from scrapper.rosario.extract import extract_pdf_url_from_html

log = logging.getLogger(__name__)


def build_normativa_pdf_url(page_url: str) -> str | None:
    """Build the direct PDF URL for a ``visualExterna.do?idNormativa=X`` page.

    Produces ``/normativa/verArchivo?tipo=pdf&id=X&modo=attachment`` directly,
    avoiding an extra HTTP request for ~95% of documents.

    Returns:
        The direct PDF download URL, or None if idNormativa is not present in the
        query string.
    """
    qs = parse_qs(urlparse(page_url).query)
    nid = qs.get("idNormativa", [None])[0]
    if nid:
        return f"{BASE_URL}/normativa/verArchivo?tipo=pdf&id={nid}&modo=attachment"
    return None


async def _fetch_page_data(
    session: aiohttp.ClientSession,
    url: str,
) -> tuple[int, str, str, str]:
    """Open *url* and return (status, content_type, html, final_url).

    Returns:
        4-tuple with HTTP status, Content-Type header, response body (empty when
        status != 200), and the final URL after redirects.
    """
    async with session.get(
        url,
        headers=HEADERS,
        timeout=aiohttp.ClientTimeout(total=30),
        allow_redirects=True,
    ) as resp:
        content_type = resp.headers.get("Content-Type", "")
        final_url = str(resp.url)
        html = await resp.text(errors="replace") if resp.status == HTTP_OK else ""
        return resp.status, content_type, html, final_url


async def _scrape_pdf_url(
    session: aiohttp.ClientSession,
    url: str,
    delay: float,
) -> str | None:
    """Fetch *url* and extract the PDF URL by scraping the response.

    Returns:
        The PDF URL, "PERMANENT" for definitive failures, or None for transient
        errors.
    """
    await asyncio.sleep(delay)
    try:
        status, content_type, html, final_url = await _fetch_page_data(session, url)
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        log.warning("Error accessing %s: %s", url, exc)
        return None

    if status == HTTP_NOT_FOUND:
        log.info("Page not found (404): %s", url)
        return "PERMANENT"
    if status != HTTP_OK:
        log.warning("HTTP %d while resolving: %s", status, url)
        return None
    if "pdf" in content_type.lower():
        return final_url
    direct = build_normativa_pdf_url(final_url)
    if direct:
        return direct
    pdf_url = extract_pdf_url_from_html(html, final_url)
    if not pdf_url:
        log.info("No PDF found on page (will be skipped on future runs): %s", url)
    return normalize_url(pdf_url) if pdf_url else "PERMANENT"


async def resolve_pdf_url(
    session: aiohttp.ClientSession,
    page_url: str,
    link_type: str,
    delay: float,
) -> str | None:
    """Dispatch to the correct PDF resolution strategy for *link_type*.

    Returns:
        The resolved PDF URL string, "PERMANENT" if the resource is definitively
        absent, or None for transient failures that should be retried.
    """
    url = normalize_url(page_url)
    if not url:
        log.warning("Invalid URL, skipping: %r", page_url)
        return None
    if link_type == "direct_pdf":
        return url
    if link_type == "normativa":
        direct = build_normativa_pdf_url(url)
        if direct:
            return direct
    return await _scrape_pdf_url(session, url, delay)
