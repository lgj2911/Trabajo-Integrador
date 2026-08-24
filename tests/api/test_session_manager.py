"""Tests for SessionManager: status transitions, single-worker invariant, logs, zip, ok_count."""

from __future__ import annotations

import asyncio
import zipfile
from typing import TYPE_CHECKING

from scrapper_api.models import SessionStatus
from scrapper_api.sessions.manager import SessionManager
from scrapper_api.sessions.store import SessionStore
from tests.api.conftest import wait_for_terminal_status

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest

    from scrapper_api.config import Settings

MANIFEST_HEADER = "downloaded_at,source,category,filename,source_url,dest_path\n"
MANIFEST_ROWS = (
    "2024-01-01T00:00:00+00:00,rosario,boletines,boletin_1_2024.pdf,http://x/1,out/1.pdf\n"
    "2024-01-01T00:00:01+00:00,rosario,boletines,boletin_2_2024.pdf,http://x/2,out/2.pdf\n"
)
_EXPECTED_OK_COUNT = 2


def _seed_manifest(settings: Settings, session_id: str) -> None:
    output_dir = settings.sessions_dir / session_id / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.csv").write_text(MANIFEST_HEADER + MANIFEST_ROWS, encoding="utf-8")


class TestSessionManagerLifecycle:
    def test_completed_session_transitions_logs_zip_and_ok_count(
        self, settings: Settings, fake_subprocess: Callable[..., list[list[str]]]
    ) -> None:
        fake_subprocess(["line one", "line two"], 0)

        async def scenario() -> None:
            store = SessionStore(settings.db_path, settings.sessions_dir)
            await store.init()
            manager = SessionManager(store, settings)
            detail = await store.create(
                source="upload", concurrency=2, delay=0.1, csv_files=["boletines.csv"]
            )
            _seed_manifest(settings, detail.id)

            queued = await store.get(detail.id)
            assert queued is not None
            assert queued.status == SessionStatus.queued

            manager.start()
            await manager.enqueue(detail.id)
            final = await wait_for_terminal_status(store, detail.id)

            assert final.status == SessionStatus.completed
            assert final.ok_count == _EXPECTED_OK_COUNT
            assert final.started_at is not None
            assert final.finished_at is not None

            log_path = settings.sessions_dir / detail.id / "execution.log"
            assert log_path.read_text(encoding="utf-8").splitlines() == ["line one", "line two"]

            result_zip = settings.sessions_dir / detail.id / "result.zip"
            assert result_zip.exists()
            with zipfile.ZipFile(result_zip) as zf:
                assert "manifest.csv" in zf.namelist()

            await manager.stop()

        asyncio.run(scenario())

    def test_failed_session_records_last_log_line_as_error(
        self, settings: Settings, fake_subprocess: Callable[..., list[list[str]]]
    ) -> None:
        fake_subprocess(["starting", "boom: something went wrong"], 1)

        async def scenario() -> None:
            store = SessionStore(settings.db_path, settings.sessions_dir)
            await store.init()
            manager = SessionManager(store, settings)
            detail = await store.create(
                source="upload", concurrency=1, delay=0.1, csv_files=["boletines.csv"]
            )
            manager.start()
            await manager.enqueue(detail.id)
            final = await wait_for_terminal_status(store, detail.id)

            assert final.status == SessionStatus.failed
            assert final.error_message == "boom: something went wrong"

            await manager.stop()

        asyncio.run(scenario())


class _BlockingFakeProcess:
    """A fake process whose wait() blocks until released (terminate() or finish())."""

    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid
        self.stdout = None
        self.terminated = False
        self._exit_event = asyncio.Event()
        self._returncode = 0

    def terminate(self) -> None:
        """Simulate SIGTERM: unblocks wait() with a signal-killed return code."""
        self.terminated = True
        self._returncode = -15
        self._exit_event.set()

    def finish(self, returncode: int = 0) -> None:
        """Let a still-blocked wait() resolve, as if the process exited on its own."""
        self._returncode = returncode
        self._exit_event.set()

    async def wait(self) -> int:
        await self._exit_event.wait()
        return self._returncode


async def _wait_for_status(
    store: SessionStore, session_id: str, status: SessionStatus, timeout: float = 5.0
) -> None:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while True:
        detail = await store.get(session_id)
        assert detail is not None
        if detail.status == status:
            return
        if loop.time() > deadline:
            msg = f"session {session_id} never reached status {status!r} (last: {detail.status!r})"
            raise AssertionError(msg)
        await asyncio.sleep(0.01)


class TestSessionManagerCancel:
    def test_cancel_running_session_terminates_process_and_marks_cancelled(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        process = _BlockingFakeProcess()

        # Must stay `async def`: it replaces asyncio.create_subprocess_exec, whose
        # callers always `await` it.
        async def fake_create_subprocess_exec(  # noqa: RUF029
            *_args: object, **_kwargs: object
        ) -> _BlockingFakeProcess:
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

        async def scenario() -> None:
            store = SessionStore(settings.db_path, settings.sessions_dir)
            await store.init()
            manager = SessionManager(store, settings)
            detail = await store.create(
                source="upload", concurrency=1, delay=0.1, csv_files=["boletines.csv"]
            )
            manager.start()
            await manager.enqueue(detail.id)
            await _wait_for_status(store, detail.id, SessionStatus.running)

            await manager.cancel(detail.id)
            assert process.terminated

            final = await wait_for_terminal_status(store, detail.id)
            assert final.status == SessionStatus.cancelled
            assert final.error_message == "Cancelled by operator"
            assert final.finished_at is not None

            await manager.stop()

        asyncio.run(scenario())

    def test_cancel_queued_session_is_skipped_without_ever_spawning_a_process(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        processes: list[_BlockingFakeProcess] = []

        # Must stay `async def`: it replaces asyncio.create_subprocess_exec, whose
        # callers always `await` it.
        async def fake_create_subprocess_exec(  # noqa: RUF029
            *_args: object, **_kwargs: object
        ) -> _BlockingFakeProcess:
            process = _BlockingFakeProcess()
            processes.append(process)
            return process

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

        async def scenario() -> None:
            store = SessionStore(settings.db_path, settings.sessions_dir)
            await store.init()
            manager = SessionManager(store, settings)

            first = await store.create(
                source="upload", concurrency=1, delay=0.1, csv_files=["boletines.csv"]
            )
            second = await store.create(
                source="upload", concurrency=1, delay=0.1, csv_files=["boletines.csv"]
            )

            manager.start()
            await manager.enqueue(first.id)
            await _wait_for_status(store, first.id, SessionStatus.running)
            await manager.enqueue(second.id)

            await manager.cancel(second.id)
            cancelled = await store.get(second.id)
            assert cancelled is not None
            assert cancelled.status == SessionStatus.cancelled
            assert cancelled.error_message == "Cancelled before it started running"
            assert cancelled.finished_at is not None
            still_running = await store.get(first.id)
            assert still_running is not None
            assert still_running.status == SessionStatus.running

            # Let `first` finish on its own; the worker then dequeues `second`,
            # sees it's no longer `queued`, and must skip it entirely.
            processes[0].finish(0)
            await wait_for_terminal_status(store, first.id)
            await asyncio.sleep(0.05)

            await manager.stop()

        asyncio.run(scenario())
        assert len(processes) == 1  # a process was only ever spawned for `first`


class _TrackingFakeProcess:
    """A fake process that stays "active" (per the test's counter) until wait() resolves."""

    def __init__(self, on_wait_done: Callable[[], None]) -> None:
        self.pid = 1
        self.stdout = None
        self._on_wait_done = on_wait_done

    async def wait(self) -> int:
        await asyncio.sleep(0.05)
        self._on_wait_done()
        return 0


class TestSessionManagerSingleWorker:
    def test_only_one_subprocess_active_at_a_time(
        self, settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        active = 0
        max_active = 0

        # Must stay `async def`: it replaces asyncio.create_subprocess_exec, whose
        # callers always `await` it.
        async def fake_create_subprocess_exec(  # noqa: RUF029
            *_args: object, **_kwargs: object
        ) -> _TrackingFakeProcess:
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)

            def _release() -> None:
                nonlocal active
                active -= 1

            return _TrackingFakeProcess(_release)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

        async def scenario() -> None:
            store = SessionStore(settings.db_path, settings.sessions_dir)
            await store.init()
            manager = SessionManager(store, settings)

            ids = [
                (
                    await store.create(
                        source="upload", concurrency=1, delay=0.1, csv_files=["boletines.csv"]
                    )
                ).id
                for _ in range(3)
            ]

            manager.start()
            for session_id in ids:
                await manager.enqueue(session_id)
            for session_id in ids:
                final = await wait_for_terminal_status(store, session_id, timeout=10.0)
                assert final.status == SessionStatus.completed
            await manager.stop()

        asyncio.run(scenario())
        # Each fake process reports itself "active" only for the instant between
        # spawn and being handed back -- if the worker ever ran two sessions
        # concurrently, two spawns would overlap and max_active would exceed 1.
        assert max_active == 1
