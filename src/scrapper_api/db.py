"""aiosqlite connection helper and schema bootstrap for the sessions database.

A single connection is opened for the process's lifetime (see
``SessionStore.init``/``close``) rather than one per call, and file locking is
disabled on it (``nolock=1``) -- see ``_connection_uri`` for why.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

import aiosqlite

if TYPE_CHECKING:
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
    ok_count INTEGER NOT NULL DEFAULT 0,
    resume_seed_count INTEGER
)
"""


def _connection_uri(db_path: Path) -> str:
    """Build a SQLite URI for *db_path* with file locking disabled.

    Production mounts DATA_DIR on Azure Files (SMB), which doesn't reliably
    support the POSIX file locks SQLite's default locking protocol needs --
    even a single, uncontended writer can get "database is locked". Disabling
    locking (``nolock=1``) is only safe because exactly one connection to this
    file is ever open at a time: ``SessionStore`` opens one connection for the
    whole process's lifetime instead of one per call (aiosqlite serializes
    every operation on a connection onto that connection's own worker thread,
    so concurrent async callers are still safe), and the single-replica
    invariant (``modules/container-app.bicep``'s hard-coded ``maxReplicas`` of
    1) guarantees at most one such process exists. Multiple *separate*
    connections to the same file with locking disabled would risk real
    corruption -- don't reintroduce a per-call ``connect()`` without also
    removing ``nolock=1``.

    Returns:
        A ``file:`` URI suitable for ``aiosqlite.connect(..., uri=True)``.
    """
    return f"file:{quote(str(db_path))}?nolock=1"


async def open_connection(db_path: Path) -> aiosqlite.Connection:
    """Open the single, long-lived connection to the sessions database.

    Creates the ``sessions`` table if it does not already exist.

    Returns:
        A connection with ``row_factory`` set to ``aiosqlite.Row``, meant to
        be kept open and reused for the process's lifetime.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(_connection_uri(db_path), uri=True)
    conn.row_factory = aiosqlite.Row
    await conn.execute(SESSIONS_SCHEMA)
    await conn.commit()
    return conn
