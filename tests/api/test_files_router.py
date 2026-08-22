"""End-to-end tests for /api/sessions/{id}/files and /api/files."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastapi import status

if TYPE_CHECKING:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from scrapper_api.config import Settings

MANIFEST_HEADER = "downloaded_at,source,category,filename,source_url,dest_path\n"
_MIN_TOTAL_TWO_SESSIONS = 2
_PAGE_SIZE_TWO = 2
_MIN_TOTAL_THREE_SEEDED = 3


def _seed_session_with_manifest(
    app: FastAPI, settings: Settings, *, category: str, filename: str
) -> str:
    async def seed() -> str:
        detail = await app.state.store.create(
            source="upload", concurrency=1, delay=0.5, csv_files=["boletines.csv"]
        )
        output_dir = settings.sessions_dir / detail.id / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        row = f"2024-01-01T00:00:00+00:00,rosario,{category},{filename},http://x/1,out/{filename}\n"
        (output_dir / "manifest.csv").write_text(MANIFEST_HEADER + row, encoding="utf-8")
        return detail.id

    return asyncio.run(seed())


class TestSessionFiles:
    def test_returns_files_for_that_session(
        self, app: FastAPI, settings: Settings, authenticated_client: TestClient
    ) -> None:
        session_id = _seed_session_with_manifest(
            app, settings, category="boletines", filename="boletin_1_2024.pdf"
        )

        response = authenticated_client.get(f"/api/sessions/{session_id}/files")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["session_id"] == session_id
        assert body["items"][0]["filename"] == "boletin_1_2024.pdf"

    def test_unknown_session_is_404(self, authenticated_client: TestClient) -> None:
        response = authenticated_client.get("/api/sessions/does-not-exist/files")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/sessions/some-id/files")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGlobalFiles:
    def test_lists_across_sessions_and_filters(
        self, app: FastAPI, settings: Settings, authenticated_client: TestClient
    ) -> None:
        session_a = _seed_session_with_manifest(
            app, settings, category="boletines", filename="boletin_1_2024.pdf"
        )
        _seed_session_with_manifest(
            app, settings, category="ordenanzas", filename="ordenanza_2_2024.pdf"
        )

        all_response = authenticated_client.get("/api/files")
        assert all_response.status_code == status.HTTP_200_OK
        assert all_response.json()["total"] >= _MIN_TOTAL_TWO_SESSIONS

        by_category = authenticated_client.get("/api/files", params={"category": "ordenanzas"})
        assert by_category.status_code == status.HTTP_200_OK
        assert all(item["category"] == "ordenanzas" for item in by_category.json()["items"])

        by_session = authenticated_client.get("/api/files", params={"session_id": session_a})
        assert by_session.status_code == status.HTTP_200_OK
        assert all(item["session_id"] == session_a for item in by_session.json()["items"])

        by_query = authenticated_client.get("/api/files", params={"q": "ordenanza_2"})
        assert by_query.status_code == status.HTTP_200_OK
        assert all("ordenanza_2" in item["filename"] for item in by_query.json()["items"])

    def test_pagination(
        self, app: FastAPI, settings: Settings, authenticated_client: TestClient
    ) -> None:
        for i in range(3):
            _seed_session_with_manifest(app, settings, category="boletines", filename=f"b{i}.pdf")

        response = authenticated_client.get("/api/files", params={"limit": 2, "offset": 0})
        body = response.json()

        assert len(body["items"]) == _PAGE_SIZE_TWO
        assert body["total"] >= _MIN_TOTAL_THREE_SEEDED

    def test_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/files")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
