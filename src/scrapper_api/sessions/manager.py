"""Single-worker execution of queued scrape sessions.

``SessionManager`` owns one :class:`asyncio.Queue` and exactly one background
consumer task: sessions are always executed strictly one at a time, in FIFO
order. This is a hard invariant -- never parallelize the worker loop -- because
the wrapped scrapper CLI is itself run as a subprocess per session and the
Rosario portal should not be hit by more than one scrape at once.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from scrapper_api.models import SessionStatus, SessionUpdate
from scrapper_api.sessions import portal_fetch
from scrapper_api.sessions.manifest_reader import read_manifest

if TYPE_CHECKING:
    from pathlib import Path

    from scrapper_api.config import Settings
    from scrapper_api.sessions.store import SessionStore

log = logging.getLogger(__name__)

#: Sentinel published on a session's log stream once it reaches a terminal status.
_END_OF_STREAM = None


class LogBroadcaster:
    """In-memory per-session fan-out of live log lines to SSE subscribers."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[str | None]]] = {}

    def subscribe(self, session_id: str) -> asyncio.Queue[str | None]:
        """Register a new subscriber queue for *session_id*.

        Returns:
            The queue that will receive published lines (``None`` on end-of-stream).
        """
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._subscribers.setdefault(session_id, []).append(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue[str | None]) -> None:
        """Remove a previously registered subscriber queue."""
        subs = self._subscribers.get(session_id)
        if subs is None:
            return
        with contextlib.suppress(ValueError):
            subs.remove(queue)
        if not subs:
            self._subscribers.pop(session_id, None)

    async def publish(self, session_id: str, line: str | None) -> None:
        """Push *line* to every live subscriber of *session_id* (``None`` = end of stream)."""
        for queue in self._subscribers.get(session_id, []):
            await queue.put(line)


@dataclass(frozen=True)
class _RunPlan:
    """Filesystem paths and run parameters for one session's CLI subprocess."""

    session_id: str
    csv_input: Path
    output_dir: Path
    checkpoint_file: Path
    log_path: Path
    concurrency: int
    delay: float


def _zip_directory(source_dir: Path, zip_path: Path) -> None:
    """Zip every file under *source_dir* into *zip_path*, with paths relative to it."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        if source_dir.exists():
            for file_path in sorted(source_dir.rglob("*")):
                if file_path.is_file():
                    zf.write(file_path, arcname=str(file_path.relative_to(source_dir)))


class SessionManager:
    """Runs queued sessions one at a time and streams their logs live."""

    def __init__(self, store: SessionStore, settings: Settings) -> None:
        self._store = store
        self._settings = settings
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._broadcaster = LogBroadcaster()
        self._worker_task: asyncio.Task[None] | None = None

    def subscribe_logs(self, session_id: str) -> asyncio.Queue[str | None]:
        """Return a queue of live log lines for *session_id* (see LogBroadcaster).

        Returns:
            The subscriber queue.
        """
        return self._broadcaster.subscribe(session_id)

    def unsubscribe_logs(self, session_id: str, queue: asyncio.Queue[str | None]) -> None:
        """Stop delivering log lines for *session_id* to *queue*."""
        self._broadcaster.unsubscribe(session_id, queue)

    async def enqueue(self, session_id: str) -> None:
        """Schedule *session_id* to run once the worker is free."""
        await self._queue.put(session_id)

    def start(self) -> None:
        """Start the single background worker task, if not already running."""
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        """Cancel the background worker task and wait for it to exit."""
        if self._worker_task is not None:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
            self._worker_task = None

    async def _worker_loop(self) -> None:
        while True:
            session_id = await self._queue.get()
            try:
                await self._run_session(session_id)
            except Exception:
                log.exception("Unhandled error running session %s", session_id)
                await self._finish(session_id, SessionStatus.failed, error_message="Internal error")
            finally:
                self._queue.task_done()

    def _session_dir(self, session_id: str) -> Path:
        return self._settings.sessions_dir / session_id

    async def _log_line(self, session_id: str, log_path: Path, text: str) -> None:
        """Append one line to execution.log and publish it to live subscribers."""
        await asyncio.to_thread(_append_line, log_path, text)
        await self._broadcaster.publish(session_id, text)

    async def _run_session(self, session_id: str) -> None:
        detail = await self._store.get(session_id)
        if detail is None:
            return

        session_dir = self._session_dir(session_id)
        csv_input = session_dir / "csv_input"
        output_dir = session_dir / "output"
        checkpoint_file = session_dir / "checkpoint.json"
        log_path = session_dir / "execution.log"
        output_dir.mkdir(parents=True, exist_ok=True)

        await self._store.update_status(
            session_id,
            SessionStatus.running,
            SessionUpdate(started_at=datetime.now(timezone.utc)),
        )

        if detail.source == "portal":

            async def on_log(text: str, log_path: Path = log_path) -> None:
                await self._log_line(session_id, log_path, text)

            try:
                await portal_fetch.fetch_all(csv_input, on_log)
            except portal_fetch.PortalFetchError as exc:
                await self._log_line(session_id, log_path, str(exc))
                await self._finish(session_id, SessionStatus.failed, error_message=str(exc))
                return

        plan = _RunPlan(
            session_id=session_id,
            csv_input=csv_input,
            output_dir=output_dir,
            checkpoint_file=checkpoint_file,
            log_path=log_path,
            concurrency=detail.concurrency,
            delay=detail.delay,
        )
        await self._run_cli_subprocess(plan)

    @staticmethod
    async def _spawn_cli_process(plan: _RunPlan) -> asyncio.subprocess.Process:
        """Start the Rosario CLI subprocess for *plan*.

        Returns:
            The spawned process handle.
        """
        return await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "scrapper",
            "rosario",
            "--output",
            str(plan.output_dir),
            "--csv-dir",
            str(plan.csv_input),
            "--checkpoint",
            str(plan.checkpoint_file),
            "--concurrency",
            str(plan.concurrency),
            "--delay",
            str(plan.delay),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

    async def _run_cli_subprocess(self, plan: _RunPlan) -> None:
        """Spawn the Rosario CLI as a subprocess and stream its output until it exits."""
        try:
            process = await self._spawn_cli_process(plan)
        except OSError as exc:
            await self._log_line(
                plan.session_id, plan.log_path, f"Failed to start scraper process: {exc}"
            )
            await self._finish(plan.session_id, SessionStatus.failed, error_message=str(exc))
            return

        await self._store.update_status(
            plan.session_id, SessionStatus.running, SessionUpdate(pid=process.pid)
        )

        last_line = ""
        if process.stdout is not None:
            async for raw_line in process.stdout:
                text = raw_line.decode("utf-8", errors="replace").rstrip("\n")
                if text:
                    last_line = text
                await self._log_line(plan.session_id, plan.log_path, text)

        return_code = await process.wait()
        ok_count = len(read_manifest(plan.session_id, plan.output_dir / "manifest.csv"))

        if return_code == 0:
            await self._finish(plan.session_id, SessionStatus.completed, ok_count=ok_count)
        else:
            error_message = last_line or f"process exited with code {return_code}"
            await self._finish(
                plan.session_id,
                SessionStatus.failed,
                ok_count=ok_count,
                error_message=error_message,
            )

    async def _finish(
        self,
        session_id: str,
        status: SessionStatus,
        *,
        ok_count: int = 0,
        error_message: str | None = None,
    ) -> None:
        await self._store.update_status(
            session_id,
            status,
            SessionUpdate(
                finished_at=datetime.now(timezone.utc),
                ok_count=ok_count,
                error_message=error_message,
            ),
        )
        session_dir = self._session_dir(session_id)
        await asyncio.to_thread(_zip_directory, session_dir / "output", session_dir / "result.zip")
        await self._broadcaster.publish(session_id, _END_OF_STREAM)


def _append_line(log_path: Path, text: str) -> None:
    """Append one line to the execution log, flushing immediately."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(text + "\n")
        f.flush()
