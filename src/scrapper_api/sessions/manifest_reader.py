"""Parse a session's manifest.csv (written by the scrapper CLI) into FileEntry rows."""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING

from scrapper_api.models import FileEntry

if TYPE_CHECKING:
    from pathlib import Path


def read_manifest(session_id: str, manifest_path: Path) -> list[FileEntry]:
    """Parse one session's manifest.csv into FileEntry rows.

    Returns:
        The rows found; an empty list if the file is missing, empty, or
        header-only.
    """
    if not manifest_path.exists():
        return []
    with manifest_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [
            FileEntry(
                session_id=session_id,
                downloaded_at=row.get("downloaded_at") or "",
                source=row.get("source") or "",
                category=row.get("category") or "",
                filename=row.get("filename") or "",
                source_url=row.get("source_url") or "",
                dest_path=row.get("dest_path") or "",
            )
            for row in reader
        ]


def read_all_manifests(sessions_dir: Path) -> list[FileEntry]:
    """Aggregate FileEntry rows across every session's manifest.csv under *sessions_dir*.

    Returns:
        All rows found across every session directory; session directories
        without a manifest contribute no rows.
    """
    if not sessions_dir.exists():
        return []
    entries: list[FileEntry] = []
    for session_dir in sorted(sessions_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        entries.extend(read_manifest(session_dir.name, session_dir / "output" / "manifest.csv"))
    return entries
