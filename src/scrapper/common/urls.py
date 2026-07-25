"""Generic URL helpers shared by the scrapers."""

from __future__ import annotations

from urllib.parse import urlparse


def normalize_url(url: str) -> str | None:
    """Normalize malformed URLs found in some CSVs.

    - 'www.foo.com/path'   -> 'http://www.foo.com/path'
    - '/www.foo.com/path'  -> 'http://www.foo.com/path'
    - 'ssl.foo.com/path'   -> 'https://ssl.foo.com/path'

    Returns:
        The normalized URL string, or None if the URL is empty or has no valid
        netloc.
    """
    url = url.strip()
    if not url:
        return None

    # Strip erroneous leading slash before the domain.
    if url.startswith(("/www.", "/ssl.")):
        url = url[1:]

    # Add scheme if missing.
    if not url.startswith("http"):
        scheme = "https" if url.startswith("ssl.") else "http"
        url = f"{scheme}://{url}"

    parsed = urlparse(url)
    if not parsed.netloc:
        return None

    return url
