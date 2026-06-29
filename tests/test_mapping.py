"""Tests for classiflow.ingestion.mapping — pure mapping/adapter functions."""

from __future__ import annotations

from datetime import date

import pytest

from classiflow.ingestion.mapping import (
    ROSARIO_DOC_TYPE_BY_CSV,
    SANTA_FE_DOC_TYPE_BY_COLLECTION,
    SANTA_FE_NORMATIVA_TYPE_BY_SLUG_PREFIX,
    _parse_rosario_date,
    _santa_fe_collection,
    _santa_fe_doc_type,
    map_rosario_row,
    map_santa_fe_document,
)
from classiflow.ingestion.schema import (
    CanonicalDocument,
    ContentFormat,
    DocumentType,
    Source,
)


# ── _parse_rosario_date ───────────────────────────────────────────────────────


class TestParseRosarioDate:
    def test_valid_date(self) -> None:
        assert _parse_rosario_date("14/05/2026") == date(2026, 5, 14)

    def test_first_of_january(self) -> None:
        assert _parse_rosario_date("01/01/2000") == date(2000, 1, 1)

    def test_none_input_returns_none(self) -> None:
        assert _parse_rosario_date(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert _parse_rosario_date("") is None

    def test_malformed_returns_none(self) -> None:
        assert _parse_rosario_date("not-a-date") is None

    def test_iso_format_returns_none(self) -> None:
        # Rosario uses DD/MM/YYYY — ISO format should fail gracefully
        assert _parse_rosario_date("2026-05-14") is None

    def test_partial_date_returns_none(self) -> None:
        assert _parse_rosario_date("14/05") is None

    def test_invalid_day_returns_none(self) -> None:
        assert _parse_rosario_date("99/01/2024") is None


# ── ROSARIO_DOC_TYPE_BY_CSV lookup table ─────────────────────────────────────


class TestRosarioDocTypeByCsv:
    @pytest.mark.parametrize(
        "csv_filename, expected_type",
        [
            ("boletines.csv", DocumentType.BOLETIN),
            ("compendios_de_boletines.csv", DocumentType.COMPENDIO_BOLETINES),
            ("convenios.csv", DocumentType.CONVENIO),
            ("declaraciones_concejo_municipal.csv", DocumentType.DECLARACION),
            ("decreto_ordenanzas.csv", DocumentType.DECRETO_ORDENANZA),
            ("decretos.csv", DocumentType.DECRETO),
            ("decretos_concejo_municipal.csv", DocumentType.DECRETO_CONCEJO),
            ("ordenanzas.csv", DocumentType.ORDENANZA),
            ("resoluciones.csv", DocumentType.RESOLUCION),
            ("resoluciones_concejo_municipal.csv", DocumentType.RESOLUCION_CONCEJO),
        ],
    )
    def test_known_csv_files(self, csv_filename: str, expected_type: DocumentType) -> None:
        assert ROSARIO_DOC_TYPE_BY_CSV[csv_filename] is expected_type

    def test_unknown_csv_not_in_dict(self) -> None:
        assert "unknown.csv" not in ROSARIO_DOC_TYPE_BY_CSV


# ── map_rosario_row ───────────────────────────────────────────────────────────


class TestMapRosarioRow:
    def _minimal_row(self) -> dict[str, str]:
        return {}

    def test_returns_canonical_document(self) -> None:
        result = map_rosario_row({}, "decretos.csv", None)
        assert isinstance(result, CanonicalDocument)

    def test_source_is_always_rosario(self) -> None:
        result = map_rosario_row({}, "decretos.csv", None)
        assert result.source is Source.ROSARIO

    def test_doc_type_from_known_csv(self) -> None:
        result = map_rosario_row({}, "ordenanzas.csv", None)
        assert result.doc_type is DocumentType.ORDENANZA

    def test_doc_type_falls_back_to_otro_for_unknown_csv(self) -> None:
        result = map_rosario_row({}, "unknown.csv", None)
        assert result.doc_type is DocumentType.OTRO

    def test_number_from_row(self) -> None:
        result = map_rosario_row({"NUMERO": "1234"}, "decretos.csv", None)
        assert result.number == "1234"

    def test_empty_number_coerced_to_none(self) -> None:
        result = map_rosario_row({"NUMERO": ""}, "decretos.csv", None)
        assert result.number is None

    def test_missing_number_is_none(self) -> None:
        result = map_rosario_row({}, "decretos.csv", None)
        assert result.number is None

    def test_year_from_row(self) -> None:
        result = map_rosario_row({"ANIO": "2024"}, "decretos.csv", None)
        assert result.year == 2024

    def test_non_digit_year_is_none(self) -> None:
        result = map_rosario_row({"ANIO": "abc"}, "decretos.csv", None)
        assert result.year is None

    def test_missing_year_is_none(self) -> None:
        result = map_rosario_row({}, "decretos.csv", None)
        assert result.year is None

    def test_subject_from_row(self) -> None:
        result = map_rosario_row({"ASUNTO": "Presupuesto"}, "decretos.csv", None)
        assert result.subject == "Presupuesto"

    def test_empty_subject_is_none(self) -> None:
        result = map_rosario_row({"ASUNTO": ""}, "decretos.csv", None)
        assert result.subject is None

    def test_sanction_date_parsed(self) -> None:
        result = map_rosario_row({"FEC_SANCION": "01/06/2024"}, "decretos.csv", None)
        assert result.sanction_date == date(2024, 6, 1)

    def test_missing_sanction_date_is_none(self) -> None:
        result = map_rosario_row({}, "decretos.csv", None)
        assert result.sanction_date is None

    def test_publication_date_parsed(self) -> None:
        result = map_rosario_row({"FEC_PUBLICACION_BOLETIN": "15/06/2024"}, "decretos.csv", None)
        assert result.publication_date == date(2024, 6, 15)

    def test_source_url_prefers_texto_vigente(self) -> None:
        row = {
            "TEXTO_VIGENTE_NORMA": "https://vigente.example.com",
            "LINK": "https://link.example.com",
        }
        result = map_rosario_row(row, "decretos.csv", None)
        assert result.source_url == "https://vigente.example.com"

    def test_source_url_falls_back_to_link(self) -> None:
        row = {"LINK": "https://link.example.com"}
        result = map_rosario_row(row, "decretos.csv", None)
        assert result.source_url == "https://link.example.com"

    def test_source_url_empty_when_both_absent(self) -> None:
        result = map_rosario_row({}, "decretos.csv", None)
        assert result.source_url == ""

    def test_content_path_passed_through(self) -> None:
        result = map_rosario_row({}, "decretos.csv", "/path/to/file.pdf")
        assert result.content_path == "/path/to/file.pdf"

    def test_content_format_pdf_when_path_given(self) -> None:
        result = map_rosario_row({}, "decretos.csv", "/path/to/file.pdf")
        assert result.content_format is ContentFormat.PDF

    def test_content_format_none_when_no_path(self) -> None:
        result = map_rosario_row({}, "decretos.csv", None)
        assert result.content_format is None

    def test_raw_metadata_captures_known_fields(self) -> None:
        row = {
            "NRO_BOLETIN": "99",
            "ANIO_BOLETIN": "2024",
            "FUE_ACTUALIZADA": "N",
        }
        result = map_rosario_row(row, "decretos.csv", None)
        assert result.raw_metadata["NRO_BOLETIN"] == "99"
        assert result.raw_metadata["ANIO_BOLETIN"] == "2024"
        assert result.raw_metadata["FUE_ACTUALIZADA"] == "N"

    def test_raw_metadata_excludes_absent_known_fields(self) -> None:
        result = map_rosario_row({}, "decretos.csv", None)
        assert result.raw_metadata == {}

    def test_raw_metadata_does_not_include_other_row_fields(self) -> None:
        row = {"NUMERO": "1", "ASUNTO": "Test", "NRO_BOLETIN": "5"}
        result = map_rosario_row(row, "decretos.csv", None)
        assert "NUMERO" not in result.raw_metadata
        assert "ASUNTO" not in result.raw_metadata
        assert "NRO_BOLETIN" in result.raw_metadata


# ── _santa_fe_collection ──────────────────────────────────────────────────────


class TestSantaFeCollection:
    def test_normativa_collection(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/decreto-dmm-123/"
        assert _santa_fe_collection(url) == "normativa"

    def test_compras_collection(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/compras-y-contrataciones/item-1/"
        assert _santa_fe_collection(url) == "compras-y-contrataciones"

    def test_convocatoria_collection(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/convocatoria/abc/"
        assert _santa_fe_collection(url) == "convocatoria"

    def test_root_url_returns_empty_or_unknown(self) -> None:
        # path is "/" → stripped to "" → split gives [""] → parts[0] == ""
        url = "https://transparencia.santafeciudad.gov.ar/"
        result = _santa_fe_collection(url)
        assert isinstance(result, str)


# ── _santa_fe_doc_type ────────────────────────────────────────────────────────


class TestSantaFeDocType:
    @pytest.mark.parametrize(
        "slug_prefix, expected_type",
        [
            ("resolucion-conjunta-001-2024", DocumentType.RESOLUCION_CONJUNTA),
            ("resolucion-dem-012-2023", DocumentType.RESOLUCION),
            ("resolucion-hcm-007-2022", DocumentType.RESOLUCION_CONCEJO),
            ("decreto-dmm-555-2021", DocumentType.DECRETO),
            ("decreto-dpb-200-2020", DocumentType.DECRETO),
            ("ordenanza-0001-2024", DocumentType.ORDENANZA),
        ],
    )
    def test_normativa_slug_patterns(self, slug_prefix: str, expected_type: DocumentType) -> None:
        url = f"https://transparencia.santafeciudad.gov.ar/normativa/{slug_prefix}/"
        from classiflow.ingestion.mapping import _santa_fe_doc_type

        assert _santa_fe_doc_type(url) is expected_type

    def test_unknown_normativa_slug_returns_otro(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/contrato-xyz-123/"
        assert _santa_fe_doc_type(url) is DocumentType.OTRO

    @pytest.mark.parametrize(
        "collection, expected_type",
        [
            ("compras-y-contrataciones", DocumentType.COMPRA),
            ("contratacion-obra", DocumentType.CONTRATACION),
            ("convocatoria", DocumentType.CONVOCATORIA),
            ("convocatorias-anteriores", DocumentType.CONVOCATORIA),
        ],
    )
    def test_non_normativa_collections(
        self, collection: str, expected_type: DocumentType
    ) -> None:
        url = f"https://transparencia.santafeciudad.gov.ar/{collection}/some-slug/"
        assert _santa_fe_doc_type(url) is expected_type

    def test_unknown_collection_returns_otro(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/random-section/some-slug/"
        assert _santa_fe_doc_type(url) is DocumentType.OTRO

    def test_resolucion_conjunta_wins_over_resolucion_dem(self) -> None:
        """Longest-first ordering must be preserved in the prefix table."""
        url = "https://transparencia.santafeciudad.gov.ar/normativa/resolucion-conjunta-1-2024/"
        assert _santa_fe_doc_type(url) is DocumentType.RESOLUCION_CONJUNTA


# ── SANTA_FE_NORMATIVA_TYPE_BY_SLUG_PREFIX ordering ──────────────────────────


class TestSantaFeSlugPrefixOrdering:
    def test_resolucion_conjunta_before_resolucion_dem(self) -> None:
        prefixes = [p for p, _ in SANTA_FE_NORMATIVA_TYPE_BY_SLUG_PREFIX]
        idx_conjunta = prefixes.index("resolucion-conjunta-")
        idx_dem = prefixes.index("resolucion-dem-")
        assert idx_conjunta < idx_dem, "resolucion-conjunta- must come before resolucion-dem-"

    def test_resolucion_conjunta_before_resolucion_hcm(self) -> None:
        prefixes = [p for p, _ in SANTA_FE_NORMATIVA_TYPE_BY_SLUG_PREFIX]
        idx_conjunta = prefixes.index("resolucion-conjunta-")
        idx_hcm = prefixes.index("resolucion-hcm-")
        assert idx_conjunta < idx_hcm


# ── map_santa_fe_document ─────────────────────────────────────────────────────


class TestMapSantaFeDocument:
    def test_returns_canonical_document(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/ordenanza-001-2024/"
        result = map_santa_fe_document(url, None, None)
        assert isinstance(result, CanonicalDocument)

    def test_source_is_always_santa_fe(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/ordenanza-001-2024/"
        result = map_santa_fe_document(url, None, None)
        assert result.source is Source.SANTA_FE

    def test_doc_type_inferred_from_url(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/ordenanza-0050-2023/"
        result = map_santa_fe_document(url, None, None)
        assert result.doc_type is DocumentType.ORDENANZA

    def test_number_is_none(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/decreto-dmm-1-2024/"
        assert map_santa_fe_document(url, None, None).number is None

    def test_year_is_none(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/decreto-dmm-1-2024/"
        assert map_santa_fe_document(url, None, None).year is None

    def test_subject_is_none(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/decreto-dmm-1-2024/"
        assert map_santa_fe_document(url, None, None).subject is None

    def test_sanction_date_is_none(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/decreto-dmm-1-2024/"
        assert map_santa_fe_document(url, None, None).sanction_date is None

    def test_publication_date_is_none(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/decreto-dmm-1-2024/"
        assert map_santa_fe_document(url, None, None).publication_date is None

    def test_source_url_preserved(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/ordenanza-001-2024/"
        result = map_santa_fe_document(url, None, None)
        assert result.source_url == url

    def test_content_path_passed_through(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/ordenanza-001-2024/"
        result = map_santa_fe_document(url, "/downloads/doc.pdf", ContentFormat.PDF)
        assert result.content_path == "/downloads/doc.pdf"

    def test_content_format_passed_through_pdf(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/ordenanza-001-2024/"
        result = map_santa_fe_document(url, "/downloads/doc.pdf", ContentFormat.PDF)
        assert result.content_format is ContentFormat.PDF

    def test_content_format_passed_through_html_text(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/ordenanza-001-2024/"
        result = map_santa_fe_document(url, "/downloads/doc.txt", ContentFormat.HTML_TEXT)
        assert result.content_format is ContentFormat.HTML_TEXT

    def test_content_format_none_when_no_path(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/ordenanza-001-2024/"
        result = map_santa_fe_document(url, None, None)
        assert result.content_format is None

    def test_raw_metadata_always_empty(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/normativa/decreto-dmm-5-2024/"
        result = map_santa_fe_document(url, None, None)
        assert result.raw_metadata == {}

    def test_compra_collection_doc_type(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/compras-y-contrataciones/compra-99/"
        result = map_santa_fe_document(url, None, None)
        assert result.doc_type is DocumentType.COMPRA

    def test_contratacion_collection_doc_type(self) -> None:
        url = "https://transparencia.santafeciudad.gov.ar/contratacion-obra/obra-1/"
        result = map_santa_fe_document(url, None, None)
        assert result.doc_type is DocumentType.CONTRATACION
