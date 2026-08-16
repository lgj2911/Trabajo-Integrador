"""Append-only CSV manifest of every successfully saved document.

Complements `checkpoint.py`: the checkpoint is an opaque resume-state set,
while the manifest is a human-browsable ledger (one row per download) meant
to travel alongside the output directory it describes.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from pathlib import Path

FIELDS = ("downloaded_at", "source", "category", "filename", "source_url", "dest_path")


class ManifestEntry(TypedDict):
    """One successfully saved document, as recorded in the manifest CSV."""

    source: str
    category: str
    filename: str
    source_url: str
    dest_path: str


def append_manifest_row(path: Path, entry: ManifestEntry) -> None:
    """Append one row to the manifest CSV at *path*, writing the header first if new."""
    is_new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(FIELDS)
        writer.writerow((
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            entry["source"],
            entry["category"],
            entry["filename"],
            entry["source_url"],
            entry["dest_path"],
        ))
