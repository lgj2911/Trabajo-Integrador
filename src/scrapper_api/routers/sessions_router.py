"""Session lifecycle endpoints: create, list, detail, live logs, and download."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, cast

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse

from scrapper.common.checkpoint import save_checkpoint
from scrapper_api.auth import require_auth
from scrapper_api.dependencies import current_manager, current_settings, current_store
from scrapper_api.models import (
    TERMINAL_SESSION_STATUSES,
    LogLine,
    SessionDetail,
    SessionEndEvent,
    SessionListResponse,
    SessionSource,
    SessionStatus,
    SessionSummary,
)
from scrapper_api.sessions import resume_seed
from scrapper_api.sessions.portal_fetch import PORTAL_CSV_FILES
from scrapper_api.sessions.upload import UploadValidationError, validate_and_extract_zip

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

_VALID_SOURCES = ("upload", "portal")
_SSE_POLL_TIMEOUT_SECONDS = 1.0


def _validate_and_extract_upload_to_tempdir(file: UploadFile) -> tuple[Path, list[str]]:
    """Validate an uploaded zip and extract it into a fresh temp directory.

    Returns:
        The temp directory path and the canonical CSV filenames it contains.

    Raises:
        UploadValidationError: if the zip fails validation.
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="scrapper_upload_"))
    try:
        extracted = validate_and_extract_zip(file.file, tmp_dir)
    except UploadValidationError:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    return tmp_dir, extracted


def _parse_resume_seed(
    resume_manifest: UploadFile | None, resume_checkpoint: UploadFile | None
) -> list[resume_seed.SeedEntry]:
    """Parse whichever of the two optional resume-seed uploads were provided.

    Returns:
        Their combined seed entries; empty if neither file was provided.
    """
    entries: list[resume_seed.SeedEntry] = []
    if resume_manifest is not None:
        entries.extend(resume_seed.parse_manifest_seed(resume_manifest.file))
    if resume_checkpoint is not None:
        entries.extend(resume_seed.parse_checkpoint_seed(resume_checkpoint.file))
    return entries


def _write_seed_checkpoint(session_dir: Path, entries: list[resume_seed.SeedEntry]) -> None:
    """Pre-seed a fresh session's checkpoint.json with *entries* before it ever runs.

    The scrapper CLI resolves its ``--output`` argument (``Path(...).resolve()``
    in ``scrapper/cli.py``, canonicalizing symlinks -- e.g. macOS's /tmp ->
    /private/tmp) before computing task keys, so the seed must be built from the
    same resolved path or its keys will never match and nothing will be skipped.
    """
    session_dir.mkdir(parents=True, exist_ok=True)
    output_dir = (session_dir / "output").resolve()
    seed = resume_seed.build_seed_checkpoint(output_dir, entries)
    save_checkpoint(seed, session_dir / "checkpoint.json")


async def resolve_resume_seed(
    resume_manifest: Annotated[UploadFile | None, File()] = None,
    resume_checkpoint: Annotated[UploadFile | None, File()] = None,
) -> list[resume_seed.SeedEntry]:
    """FastAPI dependency: parse the optional resume-seed uploads for a new session.

    A manifest.csv and/or checkpoint.json from a corpus already downloaded
    elsewhere (a prior CLI/Colab run, or a previous web session's output) --
    when given, the documents they identify get pre-seeded into the new
    session's checkpoint.json so its scrape skips them.

    Returns:
        Combined seed entries; empty if neither file was provided.

    Raises:
        HTTPException: 400 if a provided file fails validation.
    """
    if resume_manifest is None and resume_checkpoint is None:
        return []
    try:
        return await asyncio.to_thread(_parse_resume_seed, resume_manifest, resume_checkpoint)
    except resume_seed.ResumeSeedValidationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=SessionSummary)
async def create_session(  # noqa: PLR0913, PLR0917 -- FastAPI multipart endpoint, one Form/File per request field
    request: Request,
    source: Annotated[str, Form()],
    _username: Annotated[str, Depends(require_auth)],
    resume_entries: Annotated[list[resume_seed.SeedEntry], Depends(resolve_resume_seed)],
    file: Annotated[UploadFile | None, File()] = None,
    concurrency: Annotated[int, Form()] = 5,
    delay: Annotated[float, Form()] = 0.5,
) -> SessionSummary:
    """Validate the request, persist a new queued session, and enqueue it for execution.

    *resume_entries* (see ``resolve_resume_seed``) are optional: documents
    identified by an uploaded manifest.csv and/or checkpoint.json from a
    corpus already downloaded elsewhere, pre-seeded into this session's
    checkpoint.json so its scrape skips them instead of re-downloading.

    Returns:
        The freshly created session's summary.

    Raises:
        HTTPException: 400 if the source, file, concurrency, or delay is invalid.
    """
    settings = current_settings(request)
    store = current_store(request)
    manager = current_manager(request)

    if source not in _VALID_SOURCES:
        detail_msg = "source must be 'upload' or 'portal'"
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=detail_msg)
    if source == "upload" and file is None:
        detail_msg = "file is required when source=upload"
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=detail_msg)
    if concurrency < 1 or concurrency > settings.max_concurrency:
        detail_msg = f"concurrency must be between 1 and {settings.max_concurrency}"
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=detail_msg)
    if delay < settings.min_delay:
        detail_msg = f"delay must be >= {settings.min_delay}"
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=detail_msg)
    # Narrowed to SessionSource by the membership check above.
    validated_source = cast("SessionSource", source)

    tmp_dir: Path | None = None
    if source == "upload":
        assert file is not None  # narrowed by the check above
        try:
            tmp_dir, csv_files = await asyncio.to_thread(
                _validate_and_extract_upload_to_tempdir, file
            )
        except UploadValidationError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    else:
        csv_files = list(PORTAL_CSV_FILES.keys())

    resume_seed_count = (
        len({(entry.category, entry.filename) for entry in resume_entries})
        if resume_entries
        else None
    )

    detail = await store.create(
        source=validated_source,
        concurrency=concurrency,
        delay=delay,
        csv_files=csv_files,
        resume_seed_count=resume_seed_count,
    )

    session_dir = settings.sessions_dir / detail.id
    if tmp_dir is not None:
        csv_input_dir = session_dir / "csv_input"
        csv_input_dir.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.move, str(tmp_dir), str(csv_input_dir))

    if resume_entries:
        await asyncio.to_thread(_write_seed_checkpoint, session_dir, resume_entries)

    await manager.enqueue(detail.id)
    return SessionSummary(**detail.model_dump())


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    request: Request,
    _username: Annotated[str, Depends(require_auth)],
    status_filter: Annotated[SessionStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query()] = 50,
    offset: Annotated[int, Query()] = 0,
) -> SessionListResponse:
    """List sessions, newest first, optionally filtered by status.

    Returns:
        A page of session summaries plus the total matching count.
    """
    store = current_store(request)
    return await store.list_sessions(status=status_filter, limit=limit, offset=offset)


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    request: Request,
    _username: Annotated[str, Depends(require_auth)],
) -> SessionDetail:
    """Fetch one session's full detail.

    Returns:
        The session's detail.

    Raises:
        HTTPException: 404 if the session does not exist.
    """
    store = current_store(request)
    detail = await store.get(session_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    return detail


@router.post("/{session_id}/cancel", response_model=SessionDetail)
async def cancel_session(
    session_id: str,
    request: Request,
    _username: Annotated[str, Depends(require_auth)],
) -> SessionDetail:
    """Cancel a queued or running session.

    If it's the session currently running, sends SIGTERM to its CLI subprocess
    and lets the normal completion path record the final ``cancelled`` status
    once the process actually exits -- so the returned detail may still show
    ``running`` momentarily; poll ``GET /{session_id}`` (as the frontend
    already does) to see the transition land.

    Returns:
        The session's detail, reflecting whatever the cancellation could
        apply immediately.

    Raises:
        HTTPException: 404 if the session does not exist, 409 if it has
            already reached a terminal status.
    """
    store = current_store(request)
    manager = current_manager(request)

    detail = await store.get(session_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    if detail.status in TERMINAL_SESSION_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Session has already finished")

    await manager.cancel(session_id)
    updated = await store.get(session_id)
    if updated is None:  # pragma: no cover - defensive, cannot happen
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    return updated


def _read_existing_lines(log_path: Path) -> list[str]:
    """Read every line already written to *log_path*.

    Returns:
        The lines, stripped of trailing newlines; empty list if the file is missing.
    """
    if not log_path.exists():
        return []
    return log_path.read_text(encoding="utf-8").splitlines()


def _format_data_event(payload: LogLine) -> str:
    return f"data: {payload.model_dump_json()}\n\n"


def _format_end_event(payload: SessionEndEvent) -> str:
    return f"event: end\ndata: {payload.model_dump_json()}\n\n"


@router.get("/{session_id}/logs")
async def stream_logs(
    session_id: str,
    request: Request,
    _username: Annotated[str, Depends(require_auth)],
) -> StreamingResponse:
    """Server-Sent Events stream: replay the execution log, then follow it live.

    Returns:
        A ``text/event-stream`` response.

    Raises:
        HTTPException: 404 if the session does not exist.
    """
    store = current_store(request)
    manager = current_manager(request)
    settings = current_settings(request)

    detail = await store.get(session_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")

    log_path = settings.sessions_dir / session_id / "execution.log"

    async def event_stream() -> AsyncIterator[str]:
        queue = manager.subscribe_logs(session_id)
        try:
            for line in await asyncio.to_thread(_read_existing_lines, log_path):
                yield _format_data_event(LogLine(line=line, ts=datetime.now(timezone.utc)))

            while True:
                current = await store.get(session_id)
                if current is not None and current.status in TERMINAL_SESSION_STATUSES:
                    while not queue.empty():
                        item = queue.get_nowait()
                        if item is not None:
                            yield _format_data_event(
                                LogLine(line=item, ts=datetime.now(timezone.utc))
                            )
                    yield _format_end_event(SessionEndEvent(status=current.status))
                    return
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=_SSE_POLL_TIMEOUT_SECONDS)
                except asyncio.TimeoutError:
                    continue
                if item is None:
                    final = await store.get(session_id)
                    final_status = final.status if final is not None else SessionStatus.failed
                    yield _format_end_event(SessionEndEvent(status=final_status))
                    return
                yield _format_data_event(LogLine(line=item, ts=datetime.now(timezone.utc)))
        finally:
            manager.unsubscribe_logs(session_id, queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/{session_id}/download")
async def download_session(
    session_id: str,
    request: Request,
    _username: Annotated[str, Depends(require_auth)],
) -> FileResponse:
    """Stream back the zipped output directory of a completed or failed session.

    Returns:
        The session's ``result.zip`` as a file download.

    Raises:
        HTTPException: 404 if the session or its result archive is missing, or
            409 if the session has not reached a terminal status yet.
    """
    store = current_store(request)
    settings = current_settings(request)

    detail = await store.get(session_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    if detail.status not in {SessionStatus.completed, SessionStatus.failed}:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Session not completed yet")

    result_zip = settings.sessions_dir / session_id / "result.zip"
    if not result_zip.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Result archive not found")

    return FileResponse(result_zip, media_type="application/zip", filename=f"{session_id}.zip")
