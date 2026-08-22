"""Shared fixtures for scrapper_api tests: an isolated TestClient, a tmp data dir,
and a way to fake the CLI subprocess so tests never actually scrape.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import aiohttp
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from passlib.context import CryptContext
from typing_extensions import Self

from scrapper_api.app import create_app
from scrapper_api.config import Settings
from scrapper_api.models import TERMINAL_SESSION_STATUSES, SessionDetail

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from fastapi import FastAPI

    from scrapper_api.sessions.store import SessionStore

TEST_USERNAME = "admin"
TEST_PASSWORD = "correct-horse-battery-staple"  # noqa: S105 -- test fixture, not a real secret

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """A fresh, isolated DATA_DIR for one test.

    Returns:
        A tmp_path subdirectory dedicated to this test's data.
    """
    return tmp_path / "data"


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    """Settings pointed at the isolated tmp data dir, with a known test password.

    Returns:
        A Settings instance suitable for an isolated test run.
    """
    return Settings(
        data_dir=data_dir,
        webapp_username=TEST_USERNAME,
        webapp_password_hash=_pwd_context.hash(TEST_PASSWORD),
        session_secret="test-secret",  # noqa: S106 -- test fixture, not a real secret
        token_ttl_seconds=3600,
        cors_origins=["https://testserver"],
        max_concurrency=5,
        min_delay=0.1,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """A FastAPI app instance wired to the isolated test settings.

    Returns:
        A freshly built FastAPI app.
    """
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A TestClient whose lifespan (DB init, worker startup) has actually run.

    Uses an https base URL: the login cookie is set with ``Secure`` (required
    since it also carries ``SameSite=None``), and httpx's cookie jar will not
    resend a Secure cookie over a plain-http request.

    Yields:
        A TestClient with an active lifespan context.
    """
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


@pytest.fixture
def authenticated_client(client: TestClient) -> TestClient:
    """A TestClient that has already logged in (carries the session cookie).

    Returns:
        The same TestClient, post-login.
    """
    response = client.post(
        "/api/auth/login", json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
    )
    assert response.status_code == status.HTTP_200_OK
    return client


class _FakeStdout:
    """Minimal async line iterator standing in for ``Process.stdout``."""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines
        self._iter: Iterator[bytes] | None = None

    def __aiter__(self) -> _FakeStdout:
        self._iter = iter(self._lines)
        return self

    async def __anext__(self) -> bytes:
        assert self._iter is not None
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration from None


class FakeProcess:
    """Minimal stand-in for ``asyncio.subprocess.Process``."""

    def __init__(self, lines: list[str], returncode: int, pid: int) -> None:
        self.stdout = _FakeStdout([f"{line}\n".encode() for line in lines])
        self.pid = pid
        self._returncode = returncode

    async def wait(self) -> int:
        """Return the canned exit code.

        Returns:
            The configured return code.
        """
        return self._returncode


class _SubprocessState:
    """Mutable configuration for the next fake subprocess spawn."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.returncode: int = 0
        self.pid: int = 4242


@pytest.fixture
def fake_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[..., list[list[str]]]:
    """Install a fake ``asyncio.create_subprocess_exec`` and return a configurator.

    Call the returned function with ``(lines, returncode)`` to control what the
    next spawned "subprocess" prints and exits with.

    Returns:
        A configurator function which itself returns the list of recorded
        invocations (each one the list of argv strings passed), so tests can
        assert whether a subprocess was spawned at all.
    """
    calls: list[list[str]] = []
    state = _SubprocessState()

    # Must stay `async def`: it replaces asyncio.create_subprocess_exec, whose
    # callers always `await` it.
    async def fake_create_subprocess_exec(  # noqa: RUF029
        *args: object, **_kwargs: object
    ) -> FakeProcess:
        calls.append([str(a) for a in args])
        return FakeProcess(state.lines, state.returncode, state.pid)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    def configure(lines: list[str], returncode: int = 0) -> list[list[str]]:
        state.lines = lines
        state.returncode = returncode
        return calls

    return configure


class FakeAiohttpResponse:
    """Minimal async-context-manager stand-in for an aiohttp response."""

    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def read(self) -> bytes:
        """Return the canned response body.

        Returns:
            The configured bytes.
        """
        return self._body


class FakeAiohttpSession:
    """Minimal async-context-manager stand-in for an aiohttp ClientSession."""

    def __init__(self, responder: Callable[[str], FakeAiohttpResponse]) -> None:
        self._responder = responder

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    def get(self, url: str, **_kwargs: object) -> FakeAiohttpResponse:
        """Return the canned response for *url*.

        Returns:
            The response chosen by the configured responder.
        """
        return self._responder(url)


@pytest.fixture
def fake_portal_http(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Callable[[str], FakeAiohttpResponse]], None]:
    """Replace ``aiohttp.ClientSession`` with a fake driven by a per-test responder.

    Returns:
        A function that installs the given responder.
    """

    def install(responder: Callable[[str], FakeAiohttpResponse]) -> None:
        monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **k: FakeAiohttpSession(responder))  # noqa: ARG005

    return install


async def wait_for_terminal_status(
    store: SessionStore, session_id: str, timeout: float = 5.0
) -> SessionDetail:
    """Poll *store* until *session_id* reaches a terminal status.

    Returns:
        The session's final detail.

    Raises:
        AssertionError: if *timeout* elapses before a terminal status is reached.
    """
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while True:
        detail = await store.get(session_id)
        assert detail is not None
        if detail.status in TERMINAL_SESSION_STATUSES:
            return detail
        if loop.time() > deadline:
            msg = f"session {session_id} did not reach a terminal status (status={detail.status})"
            raise AssertionError(msg)
        await asyncio.sleep(0.01)
