"""Browsing endpoints for downloaded documents, per-session and aggregated."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from scrapper_api.auth import require_auth
from scrapper_api.dependencies import current_settings, current_store
from scrapper_api.models import FileEntry, FileListQuery, FileListResponse, SessionFilesResponse
from scrapper_api.sessions.manifest_reader import read_all_manifests, read_manifest

router = APIRouter(prefix="/api", tags=["files"])


@router.get("/sessions/{session_id}/files", response_model=SessionFilesResponse)
async def list_session_files(
    session_id: str,
    request: Request,
    _username: Annotated[str, Depends(require_auth)],
) -> SessionFilesResponse:
    """List every file recorded in one session's manifest.csv.

    Returns:
        The manifest rows for that session.

    Raises:
        HTTPException: 404 if the session does not exist.
    """
    store = current_store(request)
    settings = current_settings(request)

    if await store.get(session_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")

    manifest_path = settings.sessions_dir / session_id / "output" / "manifest.csv"
    items = await asyncio.to_thread(read_manifest, session_id, manifest_path)
    return SessionFilesResponse(items=items)


def _matches_filters(
    entry: FileEntry,
    *,
    category: str | None,
    source: str | None,
    session_id: str | None,
    query: str | None,
) -> bool:
    """Check whether *entry* satisfies every provided (non-None) filter.

    Returns:
        True if the entry should be included in the filtered results.
    """
    if category is not None and entry.category != category:
        return False
    if source is not None and entry.source != source:
        return False
    if session_id is not None and entry.session_id != session_id:
        return False
    return query is None or query.lower() in entry.filename.lower()


@router.get("/files", response_model=FileListResponse)
async def list_files(
    request: Request,
    _username: Annotated[str, Depends(require_auth)],
    query: Annotated[FileListQuery, Depends()],
) -> FileListResponse:
    """List downloaded files across every session, with optional filters.

    Returns:
        The matching, paginated files plus the total match count.
    """
    settings = current_settings(request)
    all_entries = await asyncio.to_thread(read_all_manifests, settings.sessions_dir)
    filtered = [
        entry
        for entry in all_entries
        if _matches_filters(
            entry,
            category=query.category,
            source=query.source,
            session_id=query.session_id,
            query=query.q,
        )
    ]
    page = filtered[query.offset : query.offset + query.limit]
    return FileListResponse(items=page, total=len(filtered))
