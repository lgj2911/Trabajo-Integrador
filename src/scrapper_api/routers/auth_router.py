"""Authentication endpoints: login, logout, and the current-user check."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from scrapper_api.auth import COOKIE_NAME, require_auth, sign_username, verify_password
from scrapper_api.dependencies import current_settings
from scrapper_api.models import AuthenticatedUser, LoginRequest, OkResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=OkResponse)
async def login(payload: LoginRequest, request: Request, response: Response) -> OkResponse:
    """Check the hardcoded credentials and set a signed session cookie on success.

    Returns:
        ``{"ok": True}`` once the cookie has been set.

    Raises:
        HTTPException: 401 if the username or password is wrong.
    """
    settings = current_settings(request)
    is_valid_user = payload.username == settings.webapp_username
    if not is_valid_user or not verify_password(payload.password, settings.webapp_password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = sign_username(payload.username, settings.session_secret)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=settings.token_ttl_seconds,
        httponly=True,
        secure=True,
        samesite="none",
    )
    return OkResponse()


@router.post("/logout", response_model=OkResponse)
async def logout(response: Response) -> OkResponse:
    """Clear the session cookie.

    Returns:
        ``{"ok": True}``.
    """
    response.delete_cookie(COOKIE_NAME)
    return OkResponse()


@router.get("/me", response_model=AuthenticatedUser)
async def me(username: Annotated[str, Depends(require_auth)]) -> AuthenticatedUser:
    """Return the currently authenticated username.

    Returns:
        The authenticated user's username.
    """
    return AuthenticatedUser(username=username)
