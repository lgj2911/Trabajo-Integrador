"""Turn a previously-downloaded corpus's manifest.csv and/or checkpoint.json into a
pre-seeded checkpoint for a new session, so it skips documents already fetched.

Both files identify a document by (category, filename) -- manifest.csv has those as
explicit columns, and checkpoint.json's keys are destination file paths where, by
construction (see scrapper.rosario.tasks.build_task_list), the parent directory name
is the category and the file name is the filename. Since every session gets a fresh,
uniquely-named output_dir, those identities are re-rooted under the *new* session's
output_dir to produce checkpoint keys the new run will actually match against.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from scrapper.common.checkpoint import SKIP_PREFIX

if TYPE_CHECKING:
    from typing import BinaryIO

#: Defensive cap on how many entries a single uploaded file may contribute,
#: mirroring upload.py's zip-bomb guard.
MAX_SEED_ENTRIES = 200_000


class ResumeSeedValidationError(Exception):
    """Raised when an uploaded manifest.csv or checkpoint.json fails validation."""


class SeedEntry(NamedTuple):
    """One previously-completed (or permanently-skipped) document identity."""

    category: str
    filename: str
    is_skip: bool


def parse_manifest_seed(file_obj: BinaryIO) -> list[SeedEntry]:
    """Parse an uploaded manifest.csv into seed entries.

    Returns:
        One entry per row with both a ``category`` and ``filename``; rows
        missing either are skipped.

    Raises:
        ResumeSeedValidationError: if the file isn't parseable CSV, has no
            usable rows, or exceeds ``MAX_SEED_ENTRIES``.
    """
    try:
        text = file_obj.read().decode("utf-8")
    except UnicodeDecodeError as exc:
        msg = "manifest.csv is not valid UTF-8 text."
        raise ResumeSeedValidationError(msg) from exc

    reader = csv.DictReader(text.splitlines())
    entries: list[SeedEntry] = []
    for row in reader:
        category = (row.get("category") or "").strip()
        filename = (row.get("filename") or "").strip()
        if not category or not filename:
            continue
        if len(entries) >= MAX_SEED_ENTRIES:
            msg = f"manifest.csv has more than {MAX_SEED_ENTRIES} usable rows."
            raise ResumeSeedValidationError(msg)
        entries.append(SeedEntry(category=category, filename=filename, is_skip=False))

    if not entries:
        msg = "manifest.csv has no rows with both a category and filename."
        raise ResumeSeedValidationError(msg)
    return entries


def parse_checkpoint_seed(file_obj: BinaryIO) -> list[SeedEntry]:
    """Parse an uploaded checkpoint.json into seed entries.

    Returns:
        One entry per key, decomposed into (category, filename) from the key's
        last two path components; ``SKIP:``-prefixed keys are carried forward
        as skip entries.

    Raises:
        ResumeSeedValidationError: if the file isn't a JSON list of strings,
            has no usable entries, or exceeds ``MAX_SEED_ENTRIES``.
    """
    try:
        raw = json.loads(file_obj.read())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        msg = "checkpoint.json is not valid JSON."
        raise ResumeSeedValidationError(msg) from exc

    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        msg = "checkpoint.json must be a JSON array of strings."
        raise ResumeSeedValidationError(msg)
    if len(raw) > MAX_SEED_ENTRIES:
        msg = f"checkpoint.json has more than {MAX_SEED_ENTRIES} entries."
        raise ResumeSeedValidationError(msg)

    entries: list[SeedEntry] = []
    for key in raw:
        is_skip = key.startswith(SKIP_PREFIX)
        path = Path(key[len(SKIP_PREFIX) :] if is_skip else key)
        if not path.name or not path.parent.name:
            continue
        entries.append(SeedEntry(category=path.parent.name, filename=path.name, is_skip=is_skip))

    if not entries:
        msg = "checkpoint.json has no usable entries."
        raise ResumeSeedValidationError(msg)
    return entries


def build_seed_checkpoint(output_dir: Path, entries: list[SeedEntry]) -> set[str]:
    """Re-root seed entries under *output_dir*, in the format checkpoint.json expects.

    Returns:
        A ``done`` set: ``str(output_dir/category/filename)`` for completed
        entries, ``SKIP:``-prefixed for permanently-skipped ones.
    """
    done: set[str] = set()
    for entry in entries:
        key = str(output_dir / entry.category / entry.filename)
        done.add(SKIP_PREFIX + key if entry.is_skip else key)
    return done
