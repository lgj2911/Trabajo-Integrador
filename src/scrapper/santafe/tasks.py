"""Build the Santa Fe download task list and destination paths."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict
from urllib.parse import urlparse

from scrapper.santafe.config import _NORMATIVA_TYPE_PATTERNS

if TYPE_CHECKING:
    from pathlib import Path


class SantaFeTask(TypedDict):
    """A single download task for the Santa Fe scraper."""

    key: str
    page_url: str
    slug: str
    dest_folder: Path


def _slug_from_url(url: str) -> str:
    """Return the last path segment of *url* (used as the file stem).

    Returns:
        The trailing slug of the URL path.
    """
    return urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]


def _collection_from_url(url: str) -> str:
    """Return the top-level collection segment of *url*.

    Returns:
        The first path segment, or "unknown" if the path is empty.
    """
    parts = urlparse(url).path.strip("/").split("/")
    return parts[0] if parts else "unknown"


def _normativa_type(slug: str) -> str:
    """Classify a normativa *slug* into a document-type folder name.

    Returns:
        The matching folder name, or "otros" when no prefix matches.
    """
    for prefix, folder in _NORMATIVA_TYPE_PATTERNS:
        if slug.startswith(prefix):
            return folder
    return "otros"


def _dest_folder(output_dir: Path, url: str) -> Path:
    """Compute the destination folder for a document *url*.

    Returns:
        ``output_dir/<collection>[/<normativa_type>]``.
    """
    collection = _collection_from_url(url)
    slug = _slug_from_url(url)
    if collection == "normativa":
        return output_dir / collection / _normativa_type(slug)
    return output_dir / collection


def build_task_list(output_dir: Path, urls: list[str]) -> list[SantaFeTask]:
    """Build a download task list from enumerated document page URLs.

    Returns:
        List of task dicts with: key (URL), page_url, slug, dest_folder.
    """
    return [
        {
            "key": url,
            "page_url": url,
            "slug": _slug_from_url(url),
            "dest_folder": _dest_folder(output_dir, url),
        }
        for url in urls
    ]
