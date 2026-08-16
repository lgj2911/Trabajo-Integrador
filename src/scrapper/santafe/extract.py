"""Extract PDF links and body text from Santa Fe WordPress pages."""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup


def extract_wp_pdf_url(html: str, page_url: str) -> str | None:
    """Find a /wp-content/uploads/*.pdf link in the page.

    Scans all tag attributes since the PDF anchor may not be in the main content
    area.

    Returns:
        Absolute PDF URL if found, else None.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(name=True):
        for attr in ("href", "src", "data"):
            val = tag.get(attr, "")
            if (
                isinstance(val, str)
                and "/wp-content/uploads/" in val
                and val.lower().endswith(".pdf")
            ):
                return val if val.startswith("http") else urljoin(page_url, val)
    return None


def extract_body_text(html: str) -> str:
    """Extract the main text content from a WordPress normativa page.

    Tries common WordPress content selectors before falling back to the full
    body.

    Returns:
        Cleaned plain text from the document body.
    """
    soup = BeautifulSoup(html, "lxml")
    for selector in ("div.entry-content", "div.post-content", "article", "div.content", "main"):
        node = soup.select_one(selector)
        if node:
            return node.get_text(separator="\n", strip=True)
    for tag in soup.find_all(["nav", "header", "footer", "script", "style"]):
        tag.decompose()
    body = soup.find("body")
    return (
        body.get_text(separator="\n", strip=True)
        if body
        else soup.get_text(separator="\n", strip=True)
    )
