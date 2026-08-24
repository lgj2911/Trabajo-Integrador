"""SQLite-backed CRUD for scrape sessions.

Every method returns Pydantic models (:class:`SessionSummary` / :class:`SessionDetail`)
-- never raw sqlite rows or dicts -- to its callers.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from scrapper_api.db import open_connection
from scrapper_api.models import (
    SessionDetail,
    SessionListResponse,
    SessionSource,
    SessionStatus,
    SessionSummary,
    SessionUpdate,
)

if TYPE_CHECKING:
    from pathlib import Path

    import aiosqlite


def _parse_dt(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp column, returning ``None`` when absent.

    Returns:
        The parsed datetime, or ``None`` if *value* is ``None``.
    """
    return datetime.fromisoformat(value) if value is not None else None


def _dir_size(path: Path) -> int:
    """Return the total size in bytes of every regular file under *path*.

    Returns:
        0 if *path* does not exist.
    """
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _is_pid_alive(pid: int) -> bool:
    """Check whether a process with the given pid is still running.

    Returns:
        True if the process exists and is signalable, False otherwise.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists, but owned by another user -- still alive from our point of view.
        return True
    return True


class SessionStore:
    """Async CRUD access to the ``sessions`` table."""

    def __init__(self, db_path: Path, sessions_dir: Path) -> None:
        self._db_path = db_path
        self._sessions_dir = sessions_dir
        self._conn: aiosqlite.Connection | None = None

    async def init(self) -> None:
        """Open the store's single long-lived connection, creating the table if needed."""
        self._conn = await open_connection(self._db_path)

    async def close(self) -> None:
        """Close the store's connection. Safe to call even if ``init`` was never called."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def _connection(self) -> aiosqlite.Connection:
        if self._conn is None:  # pragma: no cover - defensive, cannot happen via create_app
            msg = "SessionStore.init() must be called before use"
            raise RuntimeError(msg)
        return self._conn

    @staticmethod
    def _row_to_summary(row: aiosqlite.Row) -> SessionSummary:
        return SessionSummary(
            id=row["id"],
            status=SessionStatus(row["status"]),
            source=row["source"],
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=_parse_dt(row["started_at"]),
            finished_at=_parse_dt(row["finished_at"]),
            ok_count=row["ok_count"],
            error_message=row["error_message"],
        )

    def _row_to_detail(self, row: aiosqlite.Row) -> SessionDetail:
        summary = self._row_to_summary(row)
        output_dir = self._sessions_dir / row["id"] / "output"
        output_size = _dir_size(output_dir) if output_dir.exists() else None
        return SessionDetail(
            **summary.model_dump(),
            csv_files_provided=json.loads(row["csv_files_json"]),
            concurrency=row["concurrency"],
            delay=row["delay"],
            output_size_bytes=output_size,
            resume_seed_count=row["resume_seed_count"],
        )

    async def create(
        self,
        *,
        source: SessionSource,
        concurrency: int,
        delay: float,
        csv_files: list[str],
        resume_seed_count: int | None = None,
    ) -> SessionDetail:
        """Insert a new ``queued`` session and return its detail view.

        Returns:
            The freshly created session.

        Raises:
            RuntimeError: if the session cannot be read back immediately after
                insertion (defensive; should not happen in practice).
        """
        session_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        conn = self._connection
        await conn.execute(
            """
            INSERT INTO sessions (
                id, status, source, created_at, started_at, finished_at,
                concurrency, delay, csv_files_json, error_message, pid, ok_count,
                resume_seed_count
            ) VALUES (?, ?, ?, ?, NULL, NULL, ?, ?, ?, NULL, NULL, 0, ?)
            """,
            (
                session_id,
                SessionStatus.queued.value,
                source,
                created_at,
                concurrency,
                delay,
                json.dumps(csv_files),
                resume_seed_count,
            ),
        )
        await conn.commit()
        detail = await self.get(session_id)
        if detail is None:  # pragma: no cover - defensive, cannot happen
            msg = f"session {session_id} vanished right after creation"
            raise RuntimeError(msg)
        return detail

    async def get(self, session_id: str) -> SessionDetail | None:
        """Fetch one session by id.

        Returns:
            The session detail, or ``None`` if no such session exists.
        """
        cursor = await self._connection.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        return self._row_to_detail(row) if row is not None else None

    async def list_sessions(
        self,
        *,
        status: SessionStatus | None,
        limit: int,
        offset: int,
    ) -> SessionListResponse:
        """List sessions ordered by newest first, optionally filtered by status.

        Returns:
            A page of session summaries plus the total matching count.
        """
        conn = self._connection
        if status is not None:
            count_cursor = await conn.execute(
                "SELECT COUNT(*) AS n FROM sessions WHERE status = ?", (status.value,)
            )
            total_row = await count_cursor.fetchone()
            cursor = await conn.execute(
                """
                SELECT * FROM sessions WHERE status = ?
                ORDER BY created_at DESC LIMIT ? OFFSET ?
                """,
                (status.value, limit, offset),
            )
        else:
            count_cursor = await conn.execute("SELECT COUNT(*) AS n FROM sessions")
            total_row = await count_cursor.fetchone()
            cursor = await conn.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        rows = await cursor.fetchall()
        total = int(total_row["n"]) if total_row is not None else 0
        return SessionListResponse(
            items=[self._row_to_summary(row) for row in rows],
            total=total,
        )

    async def list_by_status(self, status: SessionStatus) -> list[SessionDetail]:
        """List every session currently in *status*, oldest first.

        Returns:
            The matching sessions, in creation order.
        """
        cursor = await self._connection.execute(
            "SELECT * FROM sessions WHERE status = ? ORDER BY created_at ASC",
            (status.value,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_detail(row) for row in rows]

    async def update_status(
        self,
        session_id: str,
        status: SessionStatus,
        update: SessionUpdate | None = None,
    ) -> None:
        """Update a session's status and any fields set on *update*.

        Only fields explicitly set (non-``None``) on *update* are changed; the
        others keep their current stored value. Issued as a single atomic
        UPDATE, not a sequence of statements: this store's connection is
        shared and long-lived (see ``db.py``), so a multi-statement update
        here would let a concurrent read on the same connection observe
        partially-applied state (e.g. status already ``completed`` but
        ``ok_count``/``finished_at`` not yet set).
        """
        fields = update or SessionUpdate()
        await self._connection.execute(
            """
            UPDATE sessions SET
                status = ?,
                started_at = COALESCE(?, started_at),
                finished_at = COALESCE(?, finished_at),
                error_message = COALESCE(?, error_message),
                ok_count = COALESCE(?, ok_count),
                pid = COALESCE(?, pid)
            WHERE id = ?
            """,
            (
                status.value,
                fields.started_at.isoformat() if fields.started_at is not None else None,
                fields.finished_at.isoformat() if fields.finished_at is not None else None,
                fields.error_message,
                fields.ok_count,
                fields.pid,
                session_id,
            ),
        )
        await self._connection.commit()

    async def reconcile_stale_running(self) -> list[str]:
        """Flip every ``running`` session whose pid is no longer alive to ``interrupted``.

        Returns:
            The ids of sessions that were flipped.
        """
        stale_ids: list[str] = []
        for detail in await self.list_by_status(SessionStatus.running):
            cursor = await self._connection.execute(
                "SELECT pid FROM sessions WHERE id = ?", (detail.id,)
            )
            row = await cursor.fetchone()
            pid = row["pid"] if row is not None else None
            if pid is None or not _is_pid_alive(int(pid)):
                await self.update_status(
                    detail.id,
                    SessionStatus.interrupted,
                    SessionUpdate(error_message="Server restarted while this session was running."),
                )
                stale_ids.append(detail.id)
        return stale_ids
