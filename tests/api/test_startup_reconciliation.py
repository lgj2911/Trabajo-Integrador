"""Tests for reconciling stale ``running`` sessions (dead pid) at startup."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from scrapper_api.app import create_app
from scrapper_api.models import SessionStatus, SessionUpdate
from scrapper_api.sessions.store import SessionStore

if TYPE_CHECKING:
    from scrapper_api.config import Settings


def _pid_exists(pid: int) -> bool:
    """Check whether a process with the given pid currently exists.

    Returns:
        True if the process exists (or exists but is owned by another user).
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _dead_pid() -> int:
    """Find a pid that is guaranteed not to belong to any running process.

    Returns:
        A pid for which ``os.kill(pid, 0)`` raises ``ProcessLookupError``.
    """
    candidate = 999999
    while _pid_exists(candidate):
        candidate += 1
    return candidate


class TestReconcileStaleRunning:
    def test_running_session_with_dead_pid_flips_to_interrupted(self, settings: Settings) -> None:
        async def scenario() -> None:
            store = SessionStore(settings.db_path, settings.sessions_dir)
            await store.init()
            detail = await store.create(
                source="upload", concurrency=1, delay=0.5, csv_files=["boletines.csv"]
            )
            await store.update_status(
                detail.id,
                SessionStatus.running,
                SessionUpdate(started_at=datetime.now(timezone.utc), pid=_dead_pid()),
            )

            flipped = await store.reconcile_stale_running()

            assert flipped == [detail.id]
            final = await store.get(detail.id)
            assert final is not None
            assert final.status == SessionStatus.interrupted
            assert final.error_message is not None

        asyncio.run(scenario())

    def test_running_session_with_alive_pid_is_left_alone(self, settings: Settings) -> None:
        async def scenario() -> None:
            store = SessionStore(settings.db_path, settings.sessions_dir)
            await store.init()
            detail = await store.create(
                source="upload", concurrency=1, delay=0.5, csv_files=["boletines.csv"]
            )
            await store.update_status(
                detail.id,
                SessionStatus.running,
                SessionUpdate(started_at=datetime.now(timezone.utc), pid=os.getpid()),
            )

            flipped = await store.reconcile_stale_running()

            assert flipped == []
            final = await store.get(detail.id)
            assert final is not None
            assert final.status == SessionStatus.running

        asyncio.run(scenario())


class TestStartupReconciliationViaAppLifespan:
    def test_dead_running_session_flips_when_the_app_starts(self, settings: Settings) -> None:
        async def seed() -> str:
            store = SessionStore(settings.db_path, settings.sessions_dir)
            await store.init()
            detail = await store.create(
                source="upload", concurrency=1, delay=0.5, csv_files=["boletines.csv"]
            )
            await store.update_status(
                detail.id,
                SessionStatus.running,
                SessionUpdate(started_at=datetime.now(timezone.utc), pid=_dead_pid()),
            )
            return detail.id

        session_id = asyncio.run(seed())

        app = create_app(settings)
        with TestClient(app):
            pass  # lifespan startup (and shutdown) already ran by the time this exits

        async def check() -> None:
            store = SessionStore(settings.db_path, settings.sessions_dir)
            final = await store.get(session_id)
            assert final is not None
            assert final.status == SessionStatus.interrupted

        asyncio.run(check())
