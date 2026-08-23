"""End-to-end tests for the /api/sessions endpoints (subprocess mocked, no real scraping)."""

from __future__ import annotations

import asyncio
import io
import json
import time
import zipfile
from typing import TYPE_CHECKING

from fastapi import status

from tests.api.conftest import FakeAiohttpResponse

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from fastapi import FastAPI
    from fastapi.testclient import TestClient


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _valid_upload_zip() -> bytes:
    return _zip_bytes({
        "BOLETINES.CSV": b"NUMERO,ANIO,LINK\n1,2024,http://example.com/a.pdf\n",
    })


def _wait_for_status(
    client: TestClient, session_id: str, expected: str, *, timeout: float = 5.0
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while True:
        response = client.get(f"/api/sessions/{session_id}")
        body = response.json()
        if body["status"] == expected:
            return body  # type: ignore[no-any-return]
        if time.monotonic() > deadline:
            last = body["status"]
            msg = f"session {session_id} never reached status {expected!r} (last: {last!r})"
            raise AssertionError(msg)
        time.sleep(0.02)


class TestCreateSessionUpload:
    def test_valid_zip_returns_202_and_queues_session(
        self,
        authenticated_client: TestClient,
        fake_subprocess: Callable[..., list[list[str]]],
    ) -> None:
        fake_subprocess(["done"], 0)

        response = authenticated_client.post(
            "/api/sessions",
            data={"source": "upload", "concurrency": "2", "delay": "0.2"},
            files={"file": ("csvs.zip", _valid_upload_zip(), "application/zip")},
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        body = response.json()
        assert body["source"] == "upload"
        assert body["status"] in {"queued", "running", "completed"}

        detail_response = authenticated_client.get(f"/api/sessions/{body['id']}")
        assert detail_response.status_code == status.HTTP_200_OK
        assert detail_response.json()["csv_files_provided"] == ["boletines.csv"]

        _wait_for_status(authenticated_client, body["id"], "completed")

    def test_missing_file_is_400(self, authenticated_client: TestClient) -> None:
        response = authenticated_client.post("/api/sessions", data={"source": "upload"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_zip_with_no_matching_csvs_is_400(self, authenticated_client: TestClient) -> None:
        response = authenticated_client.post(
            "/api/sessions",
            data={"source": "upload"},
            files={"file": ("csvs.zip", _zip_bytes({"readme.txt": b"hi"}), "application/zip")},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_zip_file_is_400(self, authenticated_client: TestClient) -> None:
        response = authenticated_client.post(
            "/api/sessions",
            data={"source": "upload"},
            files={"file": ("csvs.zip", b"not a zip", "application/zip")},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_bad_source_is_400(self, authenticated_client: TestClient) -> None:
        response = authenticated_client.post("/api/sessions", data={"source": "carrier-pigeon"})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_concurrency_above_max_is_400(self, authenticated_client: TestClient) -> None:
        response = authenticated_client.post(
            "/api/sessions",
            data={"source": "upload", "concurrency": "999"},
            files={"file": ("csvs.zip", _valid_upload_zip(), "application/zip")},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_delay_below_minimum_is_400(self, authenticated_client: TestClient) -> None:
        response = authenticated_client.post(
            "/api/sessions",
            data={"source": "upload", "delay": "0.0"},
            files={"file": ("csvs.zip", _valid_upload_zip(), "application/zip")},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_requires_auth(self, client: TestClient) -> None:
        response = client.post(
            "/api/sessions",
            data={"source": "upload"},
            files={"file": ("csvs.zip", _valid_upload_zip(), "application/zip")},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestCreateSessionResume:
    def test_manifest_seed_is_written_to_checkpoint_and_reported(
        self,
        authenticated_client: TestClient,
        fake_subprocess: Callable[..., list[list[str]]],
        data_dir: Path,
    ) -> None:
        fake_subprocess(["done"], 0)
        manifest_csv = (
            b"downloaded_at,source,category,filename,source_url,dest_path\n"
            b"t,rosario,boletines,a.pdf,http://x/a,/old/boletines/a.pdf\n"
        )

        response = authenticated_client.post(
            "/api/sessions",
            data={"source": "upload", "concurrency": "2", "delay": "0.2"},
            files={
                "file": ("csvs.zip", _valid_upload_zip(), "application/zip"),
                "resume_manifest": ("manifest.csv", manifest_csv, "text/csv"),
            },
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        session_id = response.json()["id"]

        detail = authenticated_client.get(f"/api/sessions/{session_id}").json()
        assert detail["resume_seed_count"] == 1

        checkpoint_path = data_dir / "sessions" / session_id / "checkpoint.json"
        seeded = json.loads(checkpoint_path.read_text())
        expected_key = str(data_dir / "sessions" / session_id / "output" / "boletines" / "a.pdf")
        assert seeded == [expected_key]

    def test_checkpoint_seed_carries_skip_entries_forward(
        self,
        authenticated_client: TestClient,
        fake_subprocess: Callable[..., list[list[str]]],
        data_dir: Path,
    ) -> None:
        fake_subprocess(["done"], 0)
        checkpoint_json = json.dumps(["SKIP:/old/output/decretos/missing.pdf"]).encode()

        response = authenticated_client.post(
            "/api/sessions",
            data={"source": "upload"},
            files={
                "file": ("csvs.zip", _valid_upload_zip(), "application/zip"),
                "resume_checkpoint": ("checkpoint.json", checkpoint_json, "application/json"),
            },
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        session_id = response.json()["id"]

        checkpoint_path = data_dir / "sessions" / session_id / "checkpoint.json"
        seeded = json.loads(checkpoint_path.read_text())
        expected_key = "SKIP:" + str(
            data_dir / "sessions" / session_id / "output" / "decretos" / "missing.pdf"
        )
        assert seeded == [expected_key]

    def test_invalid_resume_manifest_is_400(self, authenticated_client: TestClient) -> None:
        response = authenticated_client.post(
            "/api/sessions",
            data={"source": "upload"},
            files={
                "file": ("csvs.zip", _valid_upload_zip(), "application/zip"),
                "resume_manifest": ("manifest.csv", b"not,a,manifest\n", "text/csv"),
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_no_resume_files_leaves_seed_count_none(
        self,
        authenticated_client: TestClient,
        fake_subprocess: Callable[..., list[list[str]]],
    ) -> None:
        fake_subprocess(["done"], 0)

        response = authenticated_client.post(
            "/api/sessions",
            data={"source": "upload"},
            files={"file": ("csvs.zip", _valid_upload_zip(), "application/zip")},
        )

        session_id = response.json()["id"]
        detail = authenticated_client.get(f"/api/sessions/{session_id}").json()
        assert detail["resume_seed_count"] is None


class TestCreateSessionPortal:
    def test_portal_source_is_queued_and_runs(
        self,
        authenticated_client: TestClient,
        fake_subprocess: Callable[..., list[list[str]]],
        fake_portal_http: Callable[[Callable[[str], FakeAiohttpResponse]], None],
    ) -> None:
        fake_subprocess(["done"], 0)
        fake_portal_http(lambda _url: FakeAiohttpResponse(200, b"a,b\n1,2\n"))

        response = authenticated_client.post(
            "/api/sessions", data={"source": "portal", "concurrency": "1", "delay": "0.2"}
        )

        assert response.status_code == status.HTTP_202_ACCEPTED
        body = response.json()
        assert body["source"] == "portal"

        final = _wait_for_status(authenticated_client, body["id"], "completed", timeout=10.0)
        assert final["status"] == "completed"


class TestListAndGetSessions:
    def test_list_returns_created_sessions(
        self, authenticated_client: TestClient, fake_subprocess: Callable[..., list[list[str]]]
    ) -> None:
        fake_subprocess([], 0)
        create_response = authenticated_client.post(
            "/api/sessions",
            data={"source": "upload"},
            files={"file": ("csvs.zip", _valid_upload_zip(), "application/zip")},
        )
        session_id = create_response.json()["id"]

        list_response = authenticated_client.get("/api/sessions")
        assert list_response.status_code == status.HTTP_200_OK
        body = list_response.json()
        assert body["total"] >= 1
        assert any(item["id"] == session_id for item in body["items"])

    def test_get_unknown_session_is_404(self, authenticated_client: TestClient) -> None:
        response = authenticated_client.get("/api/sessions/does-not-exist")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_filters_by_status(self, authenticated_client: TestClient) -> None:
        response = authenticated_client.get("/api/sessions", params={"status": "completed"})
        assert response.status_code == status.HTTP_200_OK
        for item in response.json()["items"]:
            assert item["status"] == "completed"


class TestSessionLogsAndDownload:
    def test_logs_stream_replays_and_ends(
        self, authenticated_client: TestClient, fake_subprocess: Callable[..., list[list[str]]]
    ) -> None:
        fake_subprocess(["hello world", "second line"], 0)
        create_response = authenticated_client.post(
            "/api/sessions",
            data={"source": "upload"},
            files={"file": ("csvs.zip", _valid_upload_zip(), "application/zip")},
        )
        session_id = create_response.json()["id"]
        _wait_for_status(authenticated_client, session_id, "completed")

        logs_response = authenticated_client.get(f"/api/sessions/{session_id}/logs")
        assert logs_response.status_code == status.HTTP_200_OK
        assert logs_response.headers["content-type"].startswith("text/event-stream")
        text = logs_response.text
        assert '"line":"hello world"' in text
        assert '"line":"second line"' in text
        assert "event: end" in text
        assert '"status":"completed"' in text

    def test_logs_for_unknown_session_is_404(self, authenticated_client: TestClient) -> None:
        response = authenticated_client.get("/api/sessions/does-not-exist/logs")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_download_not_ready_is_409(
        self, app: FastAPI, authenticated_client: TestClient
    ) -> None:
        # Insert a session straight into the store (status "queued") without ever
        # enqueuing it on the manager, so it never runs and never gets a result.zip.
        async def seed() -> str:
            detail = await app.state.store.create(
                source="upload", concurrency=1, delay=0.5, csv_files=["boletines.csv"]
            )
            return detail.id

        session_id = asyncio.run(seed())

        download_response = authenticated_client.get(f"/api/sessions/{session_id}/download")
        assert download_response.status_code == status.HTTP_409_CONFLICT

    def test_download_unknown_session_is_404(self, authenticated_client: TestClient) -> None:
        response = authenticated_client.get("/api/sessions/does-not-exist/download")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_download_completed_session_returns_zip(
        self, authenticated_client: TestClient, fake_subprocess: Callable[..., list[list[str]]]
    ) -> None:
        fake_subprocess([], 0)
        create_response = authenticated_client.post(
            "/api/sessions",
            data={"source": "upload"},
            files={"file": ("csvs.zip", _valid_upload_zip(), "application/zip")},
        )
        session_id = create_response.json()["id"]
        _wait_for_status(authenticated_client, session_id, "completed")

        response = authenticated_client.get(f"/api/sessions/{session_id}/download")
        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "application/zip"
