"""Tests for parsing manifest.csv (the scrapper CLI's 6-column ledger) into FileEntry rows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from scrapper_api.sessions.manifest_reader import read_all_manifests, read_manifest

if TYPE_CHECKING:
    from pathlib import Path

HEADER = "downloaded_at,source,category,filename,source_url,dest_path\n"
ROW_1 = "2024-01-01T00:00:00+00:00,rosario,boletines,boletin_1_2024.pdf,http://x/1,out/1.pdf\n"
ROW_2 = "2024-01-01T00:00:01+00:00,rosario,ordenanzas,ordenanza_2_2024.pdf,http://x/2,out/2.pdf\n"
_EXPECTED_ROW_COUNT = 2


class TestReadManifest:
    def test_parses_rows_into_file_entries(self, tmp_path: Path) -> None:
        manifest = tmp_path / "manifest.csv"
        manifest.write_text(HEADER + ROW_1 + ROW_2, encoding="utf-8")

        entries = read_manifest("session-1", manifest)

        assert len(entries) == _EXPECTED_ROW_COUNT
        assert entries[0].session_id == "session-1"
        assert entries[0].category == "boletines"
        assert entries[0].filename == "boletin_1_2024.pdf"
        assert entries[1].category == "ordenanzas"
        assert entries[1].source_url == "http://x/2"

    def test_missing_file_returns_empty_list(self, tmp_path: Path) -> None:
        assert read_manifest("session-1", tmp_path / "does_not_exist.csv") == []

    def test_header_only_returns_empty_list(self, tmp_path: Path) -> None:
        manifest = tmp_path / "manifest.csv"
        manifest.write_text(HEADER, encoding="utf-8")

        assert read_manifest("session-1", manifest) == []

    def test_empty_file_returns_empty_list(self, tmp_path: Path) -> None:
        manifest = tmp_path / "manifest.csv"
        manifest.write_text("", encoding="utf-8")

        assert read_manifest("session-1", manifest) == []


class TestReadAllManifests:
    def test_aggregates_across_sessions(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / "sessions"
        for session_id, row in (("s1", ROW_1), ("s2", ROW_2)):
            output_dir = sessions_dir / session_id / "output"
            output_dir.mkdir(parents=True)
            (output_dir / "manifest.csv").write_text(HEADER + row, encoding="utf-8")
        (sessions_dir / "s3" / "output").mkdir(parents=True)  # no manifest -- contributes nothing

        entries = read_all_manifests(sessions_dir)

        assert {e.session_id for e in entries} == {"s1", "s2"}
        assert len(entries) == _EXPECTED_ROW_COUNT

    def test_missing_sessions_dir_returns_empty_list(self, tmp_path: Path) -> None:
        assert read_all_manifests(tmp_path / "does_not_exist") == []
