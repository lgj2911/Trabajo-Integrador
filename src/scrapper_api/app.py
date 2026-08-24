"""FastAPI application factory for the scrapper web API.

Runtime/deployment note (for whoever builds the container image): this package
adds no new *system* dependencies of its own, but at runtime it shells out to
``python -m scrapper rosario ...`` (see ``sessions/manager.py``), which pulls in
the same system dependencies as the ``scrapper`` package itself -- notably
WeasyPrint's native libraries (Pango, cairo, gdk-pixbuf, libffi/shared-mime-info)
needed for the ``html_to_pdf`` link-resolution strategy. Any image that runs
this API must install those alongside the Python dependencies, exactly as a
plain scrapper-only image would.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from scrapper_api.config import Settings, get_settings
from scrapper_api.models import HealthResponse, SessionStatus
from scrapper_api.routers import auth_router, files_router, sessions_router
from scrapper_api.sessions.manager import SessionManager
from scrapper_api.sessions.store import SessionStore

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application.

    On startup, reconciles any session left ``running`` by a previous process
    that is no longer alive (-> ``interrupted``), and re-enqueues any session
    still ``queued`` into the fresh in-memory worker queue. On shutdown, stops
    the single background worker task.

    Returns:
        The configured FastAPI instance.
    """
    resolved_settings = settings or get_settings()
    store = SessionStore(resolved_settings.db_path, resolved_settings.sessions_dir)
    manager = SessionManager(store, resolved_settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await store.init()
        await store.reconcile_stale_running()
        for queued_session in await store.list_by_status(SessionStatus.queued):
            await manager.enqueue(queued_session.id)
        manager.start()
        try:
            yield
        finally:
            await manager.stop()
            await store.close()

    app = FastAPI(title="Scrapper Web API", lifespan=lifespan)
    app.state.settings = resolved_settings
    app.state.store = store
    app.state.manager = manager

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router.router)
    app.include_router(sessions_router.router)
    app.include_router(files_router.router)

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    return app


app = create_app()
