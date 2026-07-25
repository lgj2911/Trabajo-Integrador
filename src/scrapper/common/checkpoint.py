"""Checkpoint persistence shared by the scrapers.

The checkpoint set stores two entry types:
    "<key>"        -> item successfully downloaded / saved
    "SKIP:<key>"   -> permanent failure, do not retry

``<key>`` is defined by each scraper (an absolute file path for Rosario, a
document URL for Santa Fe). This module is agnostic to its format.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

SKIP_PREFIX = "SKIP:"


def load_checkpoint(path: Path) -> set[str]:
    """Load the set of checkpoint keys from disk.

    Returns:
        Set of string keys for completed and permanently-skipped items.
    """
    if path.exists():
        with path.open(encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_checkpoint(done: set[str], path: Path) -> None:
    """Persist the checkpoint set to *path*."""
    with path.open("w", encoding="utf-8") as f:
        json.dump(list(done), f)


def is_pending(key: str, done: set[str]) -> bool:
    """Check whether an item still needs to be processed.

    Returns:
        True if the key is absent from the checkpoint (neither completed nor
        permanently skipped).
    """
    return key not in done and (SKIP_PREFIX + key) not in done
