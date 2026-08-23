"""Tests for the resume-seed parser (manifest.csv / checkpoint.json -> pre-seeded
checkpoint for a new session, re-rooted under its own output_dir)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from scrapper_api.sessions import resume_seed


def _bytes_io(text: str) -> io.BytesIO:
    return io.BytesIO(text.encode("utf-8"))


class TestParseManifestSeed:
    def test_extracts_category_and_filename_from_rows(self) -> None:
        csv_text = (
            "downloaded_at,source,category,filename,source_url,dest_path\n"
            "2026-01-01T00:00:00+00:00,rosario,boletines,a.pdf,http://x/a,/old/boletines/a.pdf\n"
            "2026-01-01T00:00:01+00:00,rosario,decretos,b.pdf,http://x/b,/old/decretos/b.pdf\n"
        )

        entries = resume_seed.parse_manifest_seed(_bytes_io(csv_text))

        assert entries == [
            resume_seed.SeedEntry(category="boletines", filename="a.pdf", is_skip=False),
            resume_seed.SeedEntry(category="decretos", filename="b.pdf", is_skip=False),
        ]

    def test_skips_rows_missing_category_or_filename(self) -> None:
        csv_text = (
            "downloaded_at,source,category,filename,source_url,dest_path\n"
            "t,rosario,,a.pdf,http://x/a,/old/a.pdf\n"
            "t,rosario,boletines,,http://x/b,/old/b.pdf\n"
            "t,rosario,decretos,c.pdf,http://x/c,/old/decretos/c.pdf\n"
        )

        entries = resume_seed.parse_manifest_seed(_bytes_io(csv_text))

        assert entries == [
            resume_seed.SeedEntry(category="decretos", filename="c.pdf", is_skip=False)
        ]

    def test_no_usable_rows_raises(self) -> None:
        csv_text = "downloaded_at,source,category,filename,source_url,dest_path\n"

        with pytest.raises(resume_seed.ResumeSeedValidationError, match="no rows"):
            resume_seed.parse_manifest_seed(_bytes_io(csv_text))

    def test_not_utf8_raises(self) -> None:
        bad = io.BytesIO(b"\xff\xfe\x00\x01")

        with pytest.raises(resume_seed.ResumeSeedValidationError, match="UTF-8"):
            resume_seed.parse_manifest_seed(bad)


class TestParseCheckpointSeed:
    def test_extracts_category_and_filename_from_paths(self) -> None:
        raw = json.dumps(["/old/output/boletines/a.pdf", "/old/output/decretos/b.pdf"])

        entries = resume_seed.parse_checkpoint_seed(_bytes_io(raw))

        assert entries == [
            resume_seed.SeedEntry(category="boletines", filename="a.pdf", is_skip=False),
            resume_seed.SeedEntry(category="decretos", filename="b.pdf", is_skip=False),
        ]

    def test_skip_prefixed_entries_carried_forward_as_skip(self) -> None:
        raw = json.dumps(["SKIP:/old/output/boletines/missing.pdf"])

        entries = resume_seed.parse_checkpoint_seed(_bytes_io(raw))

        assert entries == [
            resume_seed.SeedEntry(category="boletines", filename="missing.pdf", is_skip=True)
        ]

    def test_non_list_json_raises(self) -> None:
        with pytest.raises(resume_seed.ResumeSeedValidationError, match="JSON array"):
            resume_seed.parse_checkpoint_seed(_bytes_io(json.dumps({"a": 1})))

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(resume_seed.ResumeSeedValidationError, match="valid JSON"):
            resume_seed.parse_checkpoint_seed(_bytes_io("not json"))

    def test_no_usable_entries_raises(self) -> None:
        with pytest.raises(resume_seed.ResumeSeedValidationError, match="no usable entries"):
            resume_seed.parse_checkpoint_seed(_bytes_io(json.dumps([])))


class TestBuildSeedCheckpoint:
    def test_rewrites_entries_under_new_output_dir(self) -> None:
        output_dir = Path("/data/sessions/new-session/output")
        entries = [
            resume_seed.SeedEntry(category="boletines", filename="a.pdf", is_skip=False),
            resume_seed.SeedEntry(category="decretos", filename="b.pdf", is_skip=True),
        ]

        done = resume_seed.build_seed_checkpoint(output_dir, entries)

        assert done == {
            str(output_dir / "boletines" / "a.pdf"),
            "SKIP:" + str(output_dir / "decretos" / "b.pdf"),
        }
