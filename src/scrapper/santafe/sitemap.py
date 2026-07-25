"""Enumerate Santa Fe document URLs from the XML sitemaps."""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse
from xml.etree import ElementTree as ET  # noqa: S405

import aiohttp

from scrapper.common.config import HEADERS, HTTP_OK
from scrapper.santafe.config import _SITEMAP_NS, ALL_COLLECTIONS, SITEMAP_INDEX_URL

log = logging.getLogger(__name__)


def _sitemap_matches(sitemap_url: str, collections: tuple[str, ...]) -> bool:
    """Return True if *sitemap_url* belongs to one of the requested collections.

    Returns:
        True when the sitemap file name starts with ``<collection>-sitemap``.
    """
    filename = urlparse(sitemap_url).path.rsplit("/", 1)[-1]
    return any(filename.startswith(f"{c}-sitemap") for c in collections)


async def _fetch_xml(session: aiohttp.ClientSession, url: str) -> str | None:
    """Fetch raw XML text from *url*.

    Returns:
        The response body, or None on any HTTP or network error.
    """
    try:
        async with session.get(
            url,
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != HTTP_OK:
                log.warning("HTTP %d fetching: %s", resp.status, url)
                return None
            return await resp.text(errors="replace")
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        log.warning("Error fetching %s: %s", url, exc)
        return None


def _parse_sitemap_locs(xml_text: str) -> list[str]:
    """Parse a sitemap XML document and return its <loc> values.

    Returns:
        List of URL strings, or an empty list if the XML cannot be parsed.
    """
    try:
        root = ET.fromstring(xml_text)  # noqa: S314
    except ET.ParseError as exc:
        log.warning("Failed to parse sitemap XML: %s", exc)
        return []
    locs = [el.text for el in root.findall(".//sm:loc", _SITEMAP_NS) if el.text]
    if not locs:
        locs = [el.text for el in root.findall(".//loc") if el.text]
    return locs


async def fetch_sitemap_urls(session: aiohttp.ClientSession, sitemap_url: str) -> list[str]:
    """Fetch a sitemap and return all document URLs found in it.

    Returns:
        List of <loc> URL strings.
    """
    xml_text = await _fetch_xml(session, sitemap_url)
    return _parse_sitemap_locs(xml_text) if xml_text else []


async def enumerate_all_urls(
    session: aiohttp.ClientSession,
    collections: tuple[str, ...] = ALL_COLLECTIONS,
) -> list[str]:
    """Parse the sitemap index and collect all document URLs for the collections.

    Returns:
        Deduplicated list of document page URLs across all matched sitemaps.
    """
    log.info("Fetching sitemap index: %s", SITEMAP_INDEX_URL)
    index_locs = await fetch_sitemap_urls(session, SITEMAP_INDEX_URL)
    if not index_locs:
        log.error("Sitemap index returned no entries")
        return []

    sitemap_urls = [u for u in index_locs if _sitemap_matches(u, collections)]
    log.info(
        "Found %d sitemaps for collections: %s",
        len(sitemap_urls),
        ", ".join(collections),
    )

    all_urls: list[str] = []
    for sitemap_url in sitemap_urls:
        urls = await fetch_sitemap_urls(session, sitemap_url)
        log.info("  %s -> %d URLs", sitemap_url.rsplit("/", 1)[-1], len(urls))
        all_urls.extend(urls)

    seen: set[str] = set()
    unique: list[str] = []
    for url in all_urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)

    log.info("Total unique document URLs: %d", len(unique))
    return unique
