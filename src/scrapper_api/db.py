"""aiosqlite connection helper and schema bootstrap for the sessions database."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import aiosqlite

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

SESSIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    concurrency INTEGER NOT NULL,
    delay REAL NOT NULL,
    csv_files_json TEXT NOT NULL,
    error_message TEXT,
    pid INTEGER,
    ok_count INTEGER NOT NULL DEFAULT 0
)
"""


async def init_db(db_path: Path) -> None:
    """Create the ``sessions`` table at *db_path* if it does not already exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(SESSIONS_SCHEMA)
        await conn.commit()


@asynccontextmanager
async def connect(db_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    """Open a short-lived connection to the sessions database at *db_path*.

    Yields:
        A connection with ``row_factory`` set to ``aiosqlite.Row``.
    """
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    try:
        yield conn
    finally:
        await conn.close()
