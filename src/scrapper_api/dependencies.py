"""Typed accessors for the singletons ``create_app`` stores on ``app.state``.

Starlette's ``State`` object exposes arbitrary attributes as ``Any``, so reading
``request.app.state.store`` directly would make every call site return ``Any``
(tripping mypy's ``warn_return_any`` under strict mode). These tiny functions are
the one place that needs the resulting unavoidable ``type: ignore``; every router
calls them instead and gets a properly typed value back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import Request

    from scrapper_api.config import Settings
    from scrapper_api.sessions.manager import SessionManager
    from scrapper_api.sessions.store import SessionStore


def current_settings(request: Request) -> Settings:
    """Return the Settings instance created by create_app.

    Returns:
        The app-wide Settings.
    """
    return request.app.state.settings  # type: ignore[no-any-return]


def current_store(request: Request) -> SessionStore:
    """Return the SessionStore instance created by create_app.

    Returns:
        The app-wide SessionStore.
    """
    return request.app.state.store  # type: ignore[no-any-return]


def current_manager(request: Request) -> SessionManager:
    """Return the SessionManager instance created by create_app.

    Returns:
        The app-wide SessionManager.
    """
    return request.app.state.manager  # type: ignore[no-any-return]
