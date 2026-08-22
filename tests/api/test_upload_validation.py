"""Tests for the zip-upload validator (fuzzy filename matching, rejections, zip-bomb guard)."""

from __future__ import annotations

import io
import zipfile
from typing import TYPE_CHECKING

import pytest

from scrapper_api.sessions import upload

if TYPE_CHECKING:
    from pathlib import Path


def _make_zip(files: dict[str, bytes]) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    buf.seek(0)
    return buf


class TestMatchCanonicalFilename:
    @pytest.mark.parametrize(
        ("uploaded_name", "expected_canonical"),
        [
            ("boletines.csv", "boletines.csv"),
            ("BOLETINES.CSV", "boletines.csv"),
            ("Boletines.csv", "boletines.csv"),
            ("decreto-ordenanzas.csv", "decreto_ordenanzas.csv"),
            ("Decreto Ordenanzas.csv", "decreto_ordenanzas.csv"),
            ("resoluciones_concejo_municipal.csv", "resoluciones_concejo_municipal.csv"),
        ],
    )
    def test_matches_case_and_separator_variants(
        self, uploaded_name: str, expected_canonical: str
    ) -> None:
        assert upload.match_canonical_filename(uploaded_name) == expected_canonical

    def test_unrecognized_name_returns_none(self) -> None:
        assert upload.match_canonical_filename("not_a_scrapper_csv.csv") is None


class TestValidateAndExtractZip:
    def test_valid_zip_with_mixed_case_filenames_extracts_canonical_names(
        self, tmp_path: Path
    ) -> None:
        zip_stream = _make_zip({
            "BOLETINES.CSV": b"NUMERO,ANIO,LINK\n1,2024,http://example.com/a.pdf\n",
            "Convenios.csv": b"NUMERO,ANIO,TEXTO_VIGENTE_NORMA\n1,2024,http://example.com/b\n",
            "readme.txt": b"not a csv",
        })
        destination = tmp_path / "csv_input"

        extracted = upload.validate_and_extract_zip(zip_stream, destination)

        assert sorted(extracted) == ["boletines.csv", "convenios.csv"]
        assert (destination / "boletines.csv").read_bytes().startswith(b"NUMERO")
        assert (destination / "convenios.csv").exists()
        assert not (destination / "readme.txt").exists()

    def test_zip_with_zero_matching_csvs_is_rejected(self, tmp_path: Path) -> None:
        zip_stream = _make_zip({"readme.txt": b"hello", "data.json": b"{}"})

        with pytest.raises(upload.UploadValidationError, match="does not contain"):
            upload.validate_and_extract_zip(zip_stream, tmp_path / "csv_input")

    def test_non_zip_file_is_rejected(self, tmp_path: Path) -> None:
        not_a_zip = io.BytesIO(b"this is definitely not a zip archive")

        with pytest.raises(upload.UploadValidationError, match="not a valid zip"):
            upload.validate_and_extract_zip(not_a_zip, tmp_path / "csv_input")

    def test_oversized_zip_is_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(upload, "MAX_EXTRACTED_BYTES", 10)
        zip_stream = _make_zip({"boletines.csv": b"NUMERO,ANIO,LINK\n" + b"1,2024,x\n" * 10})

        with pytest.raises(upload.UploadValidationError, match="too large"):
            upload.validate_and_extract_zip(zip_stream, tmp_path / "csv_input")
