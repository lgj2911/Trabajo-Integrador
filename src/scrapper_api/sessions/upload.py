"""Validate and extract an uploaded ZIP of Rosario CSVs into a session's csv_input/ dir.

Filenames inside the zip are matched against the 10 canonical CSV names in
``scrapper.rosario.config.CSV_CONFIG`` using the same case/whitespace/hyphen
insensitive normalization that ``scrapper.rosario.tasks._resolve_csv_path`` uses to
locate CSVs on disk, so an upload does not need byte-exact filenames.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import BinaryIO

from scrapper.rosario.config import CSV_CONFIG

#: Zip-bomb guard: reject archives that would extract to more than this many bytes.
MAX_EXTRACTED_BYTES = 200 * 1024 * 1024


class UploadValidationError(Exception):
    """Raised when an uploaded zip archive fails validation."""


def _normalize(name: str) -> str:
    """Normalize a CSV filename for matching, mirroring scrapper.rosario.tasks.

    Returns:
        A lowercase form with runs of whitespace/hyphens collapsed to underscores.
    """
    return re.sub(r"[\s\-]+", "_", name).lower()


_CANONICAL_BY_NORMALIZED: dict[str, str] = {_normalize(name): name for name in CSV_CONFIG}


def match_canonical_filename(name: str) -> str | None:
    """Map an arbitrary filename to one of the 10 canonical Rosario CSV names.

    Returns:
        The canonical filename (e.g. ``"boletines.csv"``) if *name* matches one
        of the configured categories, ignoring case, whitespace, and hyphens;
        ``None`` if it matches none of them.
    """
    return _CANONICAL_BY_NORMALIZED.get(_normalize(name))


def validate_and_extract_zip(file_obj: BinaryIO, destination: Path) -> list[str]:
    """Validate an uploaded zip and extract its matching CSVs into *destination*.

    Returns:
        The canonical filenames that were extracted (at least one, guaranteed).

    Raises:
        UploadValidationError: if the stream is not a valid zip, none of its
            entries match a canonical CSV name, or the matching entries would
            extract beyond ``MAX_EXTRACTED_BYTES``.
    """
    if not zipfile.is_zipfile(file_obj):
        msg = "Uploaded file is not a valid zip archive."
        raise UploadValidationError(msg)
    file_obj.seek(0)

    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(file_obj) as zf:
        matches: list[tuple[zipfile.ZipInfo, str]] = []
        total_size = 0
        for info in zf.infolist():
            if info.is_dir():
                continue
            canonical = match_canonical_filename(Path(info.filename).name)
            if canonical is None:
                continue
            total_size += info.file_size
            matches.append((info, canonical))

        if not matches:
            msg = "Zip archive does not contain any of the recognized Rosario CSV files."
            raise UploadValidationError(msg)
        if total_size > MAX_EXTRACTED_BYTES:
            msg = f"Zip archive is too large to extract ({total_size} bytes)."
            raise UploadValidationError(msg)

        extracted: list[str] = []
        for info, canonical in matches:
            with zf.open(info) as src, (destination / canonical).open("wb") as dst:
                dst.write(src.read())
            extracted.append(canonical)

    return extracted
