"""Tests for login/logout/me and the signed-cookie auth dependency."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest
from fastapi import status

from scrapper_api.auth import COOKIE_NAME, sign_username, unsign_username
from tests.api.conftest import TEST_PASSWORD, TEST_USERNAME

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


class TestLogin:
    def test_success_sets_cookie_and_returns_ok(self, client: TestClient) -> None:
        response = client.post(
            "/api/auth/login", json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"ok": True}
        assert COOKIE_NAME in response.cookies

    @pytest.mark.parametrize(
        ("username", "password"),
        [
            (TEST_USERNAME, "wrong-password"),
            ("someone-else", TEST_PASSWORD),
            ("", ""),
        ],
    )
    def test_failure_returns_401(self, client: TestClient, username: str, password: str) -> None:
        response = client.post("/api/auth/login", json={"username": username, "password": password})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json() == {"detail": "Invalid credentials"}


class TestLogout:
    def test_clears_cookie(self, authenticated_client: TestClient) -> None:
        response = authenticated_client.post("/api/auth/logout")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"ok": True}

        me_response = authenticated_client.get("/api/auth/me")
        assert me_response.status_code == status.HTTP_401_UNAUTHORIZED


class TestProtectedRoutes:
    def test_me_without_cookie_is_401(self, client: TestClient) -> None:
        response = client.get("/api/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json() == {"detail": "Not authenticated"}

    def test_me_with_valid_cookie_is_200(self, authenticated_client: TestClient) -> None:
        response = authenticated_client.get("/api/auth/me")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"authenticated": True, "username": TEST_USERNAME}

    def test_sessions_list_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/sessions")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestSignedCookieExpiry:
    def test_round_trip(self) -> None:
        token = sign_username(TEST_USERNAME, "secret")
        assert unsign_username(token, "secret", max_age_seconds=3600) == TEST_USERNAME

    def test_wrong_secret_rejected(self) -> None:
        token = sign_username(TEST_USERNAME, "secret")
        assert unsign_username(token, "different-secret", max_age_seconds=3600) is None

    def test_expired_token_rejected(self) -> None:
        token = sign_username(TEST_USERNAME, "secret")
        # itsdangerous truncates its embedded timestamp to whole seconds, so sleep
        # well past one extra second to guarantee the max_age check is exceeded.
        time.sleep(2.1)
        assert unsign_username(token, "secret", max_age_seconds=1) is None
