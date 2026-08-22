"""Cookie-based authentication for the single hardcoded web-app user.

A signed, timestamped cookie (via ``itsdangerous.TimestampSigner``) stands in for a
full JWT: there is exactly one user account, so there is no audience/issuer/JWKS to
manage. The password itself is checked with bcrypt via passlib.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from passlib.context import CryptContext

COOKIE_NAME = "scrapper_session"

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Check *plain_password* against a bcrypt *password_hash*.

    Returns:
        True if the password matches and a hash was configured, False otherwise.
    """
    if not password_hash:
        return False
    return bool(_pwd_context.verify(plain_password, password_hash))


def sign_username(username: str, secret: str) -> str:
    """Produce a signed, timestamped cookie value carrying *username*.

    Returns:
        The signed token string.
    """
    signer = TimestampSigner(secret)
    return signer.sign(username.encode("utf-8")).decode("utf-8")


def unsign_username(token: str, secret: str, max_age_seconds: int) -> str | None:
    """Recover the username from a signed cookie token.

    Returns:
        The username if the signature is valid and not expired, else ``None``.
    """
    signer = TimestampSigner(secret)
    try:
        raw = signer.unsign(token, max_age=max_age_seconds)
    except (BadSignature, SignatureExpired):
        return None
    return raw.decode("utf-8")


def require_auth(request: Request) -> str:
    """FastAPI dependency enforcing a valid signed session cookie.

    Returns:
        The authenticated username.

    Raises:
        HTTPException: 401 if the cookie is missing, invalid, or expired.
    """
    settings = request.app.state.settings
    token = request.cookies.get(COOKIE_NAME)
    username = (
        unsign_username(token, settings.session_secret, settings.token_ttl_seconds)
        if token is not None
        else None
    )
    if username is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return username
