"""Extract the real PDF URL from a Rosario portal HTML page."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from bs4 import BeautifulSoup

if TYPE_CHECKING:
    from collections.abc import Callable

_PDF_URL_PATTERNS = (
    r'["\']([^"\']*verArchivo[^"\']*)["\']',
    r'["\']([^"\']*getPdf[^"\']*)["\']',
)

_TAG_ATTRS = [
    ("a", "href"),
    ("iframe", "src"),
    ("embed", "src"),
    ("object", "data"),
    ("frame", "src"),
]


def _is_pdf_url(u: str) -> bool:
    """Return True if *u* looks like a Rosario portal PDF URL.

    Returns:
        True when the URL contains a known PDF-serving path or ends in .pdf.
    """
    return bool(
        u
        and (
            "verArchivo" in u or "getPdf" in u or "documento.do" in u or u.lower().endswith(".pdf")
        )
    )


def _search_tagged_elements(
    soup: BeautifulSoup,
    resolve: Callable[[str], str],
) -> str | None:
    """Check known tag/attribute pairs (a, iframe, embed, object, frame).

    Returns:
        First matching PDF URL found, or None.
    """
    for tag, attr in _TAG_ATTRS:
        for el in soup.find_all(tag):
            val = el.get(attr, "")
            if isinstance(val, str) and _is_pdf_url(val):
                return resolve(val)
    return None


def _search_all_attrs(
    soup: BeautifulSoup,
    resolve: Callable[[str], str],
) -> str | None:
    """Sweep every element and every attribute looking for a PDF URL.

    Returns:
        First matching PDF URL found, or None.
    """
    for el in soup.find_all(name=True):
        for val in el.attrs.values():
            if isinstance(val, str) and _is_pdf_url(val):
                return resolve(val)
    return None


def _search_raw_html(
    html: str,
    resolve: Callable[[str], str],
) -> str | None:
    """Regex fallback: search raw HTML for PDF URLs in scripts or data-attributes.

    Returns:
        First matching PDF URL found, or None.
    """
    for pattern in _PDF_URL_PATTERNS:
        matches = re.findall(pattern, html)
        if matches:
            return resolve(matches[0])
    return None


def extract_pdf_url_from_html(html: str, page_url: str) -> str | None:
    """Search for the PDF URL in the HTML of a Rosario portal page.

    Tries three strategies in order: known tag/attr pairs, generic attribute
    sweep, then raw HTML regex.

    Returns:
        The absolute PDF URL if found, or None if no PDF link is detected.
    """
    soup: BeautifulSoup = BeautifulSoup(html, "lxml")

    def resolve(href: str) -> str:
        return href if href.startswith("http") else urljoin(page_url, href)

    return (
        _search_tagged_elements(soup, resolve)
        or _search_all_attrs(soup, resolve)
        or _search_raw_html(html, resolve)
    )
