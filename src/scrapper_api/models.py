"""Pydantic models shared across the scrapper web API.

Every shape that crosses a process/API/DB boundary is modeled here as a
``pydantic.BaseModel`` (or ``enum.Enum``) rather than as a bare ``dict``.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 -- pydantic needs this at runtime to build schemas
from enum import Enum
from typing import Literal

from pydantic import BaseModel


class SessionStatus(str, Enum):
    """Lifecycle states of a scrape session."""

    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    interrupted = "interrupted"


#: Statuses that will never change again.
TERMINAL_SESSION_STATUSES = frozenset({
    SessionStatus.completed,
    SessionStatus.failed,
    SessionStatus.interrupted,
})

#: Origin of the CSV input for a session: a user-uploaded zip, or a live fetch
#: from Rosario's open-data portal.
SessionSource = Literal["upload", "portal"]


class SessionSummary(BaseModel):
    """Lightweight view of a session, used in list and creation responses."""

    id: str
    status: SessionStatus
    source: SessionSource
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    ok_count: int
    error_message: str | None


class SessionDetail(SessionSummary):
    """Full view of a session, including its run configuration."""

    csv_files_provided: list[str]
    concurrency: int
    delay: float
    output_size_bytes: int | None
    resume_seed_count: int | None


class SessionListResponse(BaseModel):
    """Paginated listing of sessions."""

    items: list[SessionSummary]
    total: int


class FileEntry(BaseModel):
    """One downloaded document, as recorded in a session's manifest.csv."""

    session_id: str
    downloaded_at: str
    source: str
    category: str
    filename: str
    source_url: str
    dest_path: str


class FileListResponse(BaseModel):
    """Paginated listing of downloaded files."""

    items: list[FileEntry]
    total: int


class SessionFilesResponse(BaseModel):
    """Response body of ``GET /api/sessions/{id}/files`` -- unpaginated."""

    items: list[FileEntry]


class LoginRequest(BaseModel):
    """Body of ``POST /api/auth/login``."""

    username: str
    password: str


class OkResponse(BaseModel):
    """Generic success acknowledgement."""

    ok: bool = True


class AuthenticatedUser(BaseModel):
    """Response body of ``GET /api/auth/me`` when a valid session cookie is present."""

    authenticated: Literal[True] = True
    username: str


class ErrorResponse(BaseModel):
    """Standard error body, matching FastAPI's default ``{"detail": ...}`` shape."""

    detail: str


class HealthResponse(BaseModel):
    """Response body of ``GET /api/health``."""

    status: Literal["ok"] = "ok"


class LogLine(BaseModel):
    """One line of a session's execution log, as streamed over SSE."""

    line: str
    ts: datetime


class SessionEndEvent(BaseModel):
    """Terminal SSE event payload sent once a session's log stream ends."""

    status: SessionStatus


class SessionUpdate(BaseModel):
    """Optional fields to change on a session; unset (``None``) fields are left as-is."""

    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    ok_count: int | None = None
    pid: int | None = None


class FileListQuery(BaseModel):
    """Query parameters accepted by ``GET /api/files``."""

    category: str | None = None
    source: str | None = None
    session_id: str | None = None
    q: str | None = None
    limit: int = 100
    offset: int = 0
