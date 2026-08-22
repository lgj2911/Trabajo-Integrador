"""Tests for fetching Rosario's open-data CSVs (mocked HTTP layer, no real network calls)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from scrapper_api.models import SessionStatus
from scrapper_api.sessions import portal_fetch
from scrapper_api.sessions.manager import SessionManager
from scrapper_api.sessions.store import SessionStore
from tests.api.conftest import FakeAiohttpResponse, wait_for_terminal_status

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from scrapper_api.config import Settings


class TestFetchAll:
    def test_all_ten_succeed(
        self,
        tmp_path: Path,
        fake_portal_http: Callable[[Callable[[str], FakeAiohttpResponse]], None],
    ) -> None:
        fake_portal_http(lambda _url: FakeAiohttpResponse(200, b"a,b\n1,2\n"))
        destination = tmp_path / "csv_input"
        log_lines: list[str] = []

        # Must stay `async def`: fetch_all's LogSink type is Callable[[str], Awaitable[None]].
        async def on_log(text: str) -> None:  # noqa: RUF029
            log_lines.append(text)

        written = asyncio.run(portal_fetch.fetch_all(destination, on_log))

        assert sorted(written) == sorted(portal_fetch.PORTAL_CSV_FILES.keys())
        for canonical_name in portal_fetch.PORTAL_CSV_FILES:
            assert (destination / canonical_name).read_bytes() == b"a,b\n1,2\n"
        assert any("Fetched" in line for line in log_lines)

    def test_one_fails_after_retries_raises_and_stops(
        self,
        tmp_path: Path,
        fake_portal_http: Callable[[Callable[[str], FakeAiohttpResponse]], None],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(portal_fetch, "_RETRY_DELAY_SECONDS", 0.0)
        failing_resource = portal_fetch.PORTAL_CSV_FILES["ordenanzas.csv"]
        attempts: list[str] = []

        def responder(url: str) -> FakeAiohttpResponse:
            attempts.append(url)
            if failing_resource in url:
                return FakeAiohttpResponse(500, b"")
            return FakeAiohttpResponse(200, b"a,b\n1,2\n")

        fake_portal_http(responder)

        destination = tmp_path / "csv_input"
        log_lines: list[str] = []

        # Must stay `async def`: fetch_all's LogSink type is Callable[[str], Awaitable[None]].
        async def on_log(text: str) -> None:  # noqa: RUF029
            log_lines.append(text)

        with pytest.raises(portal_fetch.PortalFetchError, match=r"ordenanzas\.csv"):
            asyncio.run(portal_fetch.fetch_all(destination, on_log))

        # Retried MAX_ATTEMPTS times for the failing resource, then stopped --
        # later CSVs in the iteration order were never attempted.
        failing_attempts = [u for u in attempts if failing_resource in u]
        assert len(failing_attempts) == portal_fetch.MAX_ATTEMPTS
        assert not (destination / "ordenanzas.csv").exists()
        assert not (destination / "resoluciones.csv").exists()
        assert (destination / "boletines.csv").exists()


class TestPortalFetchFailureViaSessionManager:
    def test_session_fails_without_spawning_subprocess(
        self,
        settings: Settings,
        fake_portal_http: Callable[[Callable[[str], FakeAiohttpResponse]], None],
        fake_subprocess: Callable[..., list[list[str]]],
    ) -> None:
        recorded_calls = fake_subprocess([], 0)

        def responder(_url: str) -> FakeAiohttpResponse:
            return FakeAiohttpResponse(500, b"")

        fake_portal_http(responder)

        async def scenario() -> None:
            store = SessionStore(settings.db_path, settings.sessions_dir)
            await store.init()
            manager = SessionManager(store, settings)
            detail = await store.create(
                source="portal",
                concurrency=2,
                delay=0.1,
                csv_files=list(portal_fetch.PORTAL_CSV_FILES.keys()),
            )
            manager.start()
            await manager.enqueue(detail.id)
            final = await wait_for_terminal_status(store, detail.id, timeout=15.0)
            assert final.status == SessionStatus.failed
            assert final.error_message is not None
            assert "Rosario open-data portal" in final.error_message
            await manager.stop()

        asyncio.run(scenario())
        assert recorded_calls == []
