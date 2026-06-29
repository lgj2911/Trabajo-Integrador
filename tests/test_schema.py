"""Tests for classiflow.ingestion.schema — enums and CanonicalDocument dataclass."""

from __future__ import annotations

from datetime import date

import pytest

from classiflow.ingestion.schema import (
    CanonicalDocument,
    ContentFormat,
    DocumentType,
    Source,
)


# ── Source enum ──────────────────────────────────────────────────────────────


class TestSourceEnum:
    def test_rosario_value(self) -> None:
        assert Source.ROSARIO == "rosario"

    def test_santa_fe_value(self) -> None:
        assert Source.SANTA_FE == "santa_fe"

    def test_is_str_subclass(self) -> None:
        assert isinstance(Source.ROSARIO, str)

    def test_all_members(self) -> None:
        members = {m.value for m in Source}
        assert members == {"rosario", "santa_fe"}

    def test_from_string(self) -> None:
        assert Source("rosario") is Source.ROSARIO
        assert Source("santa_fe") is Source.SANTA_FE

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            Source("unknown")


# ── ContentFormat enum ───────────────────────────────────────────────────────


class TestContentFormatEnum:
    def test_pdf_value(self) -> None:
        assert ContentFormat.PDF == "pdf"

    def test_html_text_value(self) -> None:
        assert ContentFormat.HTML_TEXT == "html_text"

    def test_is_str_subclass(self) -> None:
        assert isinstance(ContentFormat.PDF, str)

    def test_all_members(self) -> None:
        members = {m.value for m in ContentFormat}
        assert members == {"pdf", "html_text"}

    def test_from_string(self) -> None:
        assert ContentFormat("pdf") is ContentFormat.PDF
        assert ContentFormat("html_text") is ContentFormat.HTML_TEXT


# ── DocumentType enum ────────────────────────────────────────────────────────


class TestDocumentTypeEnum:
    _EXPECTED_VALUES = {
        "decreto",
        "decreto_concejo",
        "ordenanza",
        "decreto_ordenanza",
        "resolucion",
        "resolucion_concejo",
        "resolucion_conjunta",
        "convenio",
        "declaracion",
        "boletin",
        "compendio_boletines",
        "compra",
        "contratacion",
        "convocatoria",
        "otro",
    }

    def test_all_expected_values_present(self) -> None:
        actual = {m.value for m in DocumentType}
        assert actual == self._EXPECTED_VALUES

    def test_is_str_subclass(self) -> None:
        assert isinstance(DocumentType.DECRETO, str)

    @pytest.mark.parametrize(
        "value",
        [
            "decreto",
            "decreto_concejo",
            "ordenanza",
            "decreto_ordenanza",
            "resolucion",
            "resolucion_concejo",
            "resolucion_conjunta",
            "convenio",
            "declaracion",
            "boletin",
            "compendio_boletines",
            "compra",
            "contratacion",
            "convocatoria",
            "otro",
        ],
    )
    def test_round_trip_from_string(self, value: str) -> None:
        assert DocumentType(value).value == value

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            DocumentType("not_a_type")


# ── CanonicalDocument dataclass ───────────────────────────────────────────────


_FULL_DOC = CanonicalDocument(
    source=Source.ROSARIO,
    doc_type=DocumentType.DECRETO,
    number="123",
    year=2024,
    subject="Presupuesto municipal",
    sanction_date=date(2024, 3, 15),
    publication_date=date(2024, 3, 20),
    source_url="https://www.rosario.gob.ar/normativa/verArchivo?tipo=pdf&id=123",
    content_path="/downloads/decreto_123.pdf",
    content_format=ContentFormat.PDF,
    raw_metadata={"NRO_BOLETIN": "42", "ANIO_BOLETIN": "2024", "FUE_ACTUALIZADA": "S"},
)


class TestCanonicalDocumentCreation:
    def test_source_field(self) -> None:
        assert _FULL_DOC.source is Source.ROSARIO

    def test_doc_type_field(self) -> None:
        assert _FULL_DOC.doc_type is DocumentType.DECRETO

    def test_number_field(self) -> None:
        assert _FULL_DOC.number == "123"

    def test_year_field(self) -> None:
        assert _FULL_DOC.year == 2024

    def test_subject_field(self) -> None:
        assert _FULL_DOC.subject == "Presupuesto municipal"

    def test_sanction_date_field(self) -> None:
        assert _FULL_DOC.sanction_date == date(2024, 3, 15)

    def test_publication_date_field(self) -> None:
        assert _FULL_DOC.publication_date == date(2024, 3, 20)

    def test_source_url_field(self) -> None:
        assert "rosario.gob.ar" in _FULL_DOC.source_url

    def test_content_path_field(self) -> None:
        assert _FULL_DOC.content_path == "/downloads/decreto_123.pdf"

    def test_content_format_field(self) -> None:
        assert _FULL_DOC.content_format is ContentFormat.PDF

    def test_raw_metadata_field(self) -> None:
        assert _FULL_DOC.raw_metadata["NRO_BOLETIN"] == "42"
        assert _FULL_DOC.raw_metadata["ANIO_BOLETIN"] == "2024"


class TestCanonicalDocumentNullableFields:
    def test_number_can_be_none(self) -> None:
        doc = CanonicalDocument(
            source=Source.SANTA_FE,
            doc_type=DocumentType.OTRO,
            number=None,
            year=None,
            subject=None,
            sanction_date=None,
            publication_date=None,
            source_url="https://example.com",
            content_path=None,
            content_format=None,
        )
        assert doc.number is None
        assert doc.year is None
        assert doc.subject is None
        assert doc.sanction_date is None
        assert doc.publication_date is None
        assert doc.content_path is None
        assert doc.content_format is None

    def test_raw_metadata_defaults_to_empty_dict(self) -> None:
        doc = CanonicalDocument(
            source=Source.SANTA_FE,
            doc_type=DocumentType.OTRO,
            number=None,
            year=None,
            subject=None,
            sanction_date=None,
            publication_date=None,
            source_url="https://example.com",
            content_path=None,
            content_format=None,
        )
        assert doc.raw_metadata == {}

    def test_each_call_gets_independent_raw_metadata(self) -> None:
        """Verify the default_factory gives each instance its own dict."""
        doc_a = CanonicalDocument(
            source=Source.ROSARIO,
            doc_type=DocumentType.DECRETO,
            number=None,
            year=None,
            subject=None,
            sanction_date=None,
            publication_date=None,
            source_url="https://a.com",
            content_path=None,
            content_format=None,
        )
        doc_b = CanonicalDocument(
            source=Source.ROSARIO,
            doc_type=DocumentType.DECRETO,
            number=None,
            year=None,
            subject=None,
            sanction_date=None,
            publication_date=None,
            source_url="https://b.com",
            content_path=None,
            content_format=None,
        )
        assert doc_a.raw_metadata is not doc_b.raw_metadata


class TestCanonicalDocumentImmutability:
    def test_frozen_prevents_attribute_assignment(self) -> None:
        with pytest.raises((AttributeError, TypeError)):
            _FULL_DOC.number = "999"  # type: ignore[misc]

    def test_frozen_prevents_raw_metadata_reassignment(self) -> None:
        with pytest.raises((AttributeError, TypeError)):
            _FULL_DOC.raw_metadata = {}  # type: ignore[misc]


class TestCanonicalDocumentEquality:
    def test_equal_docs_compare_equal(self) -> None:
        doc1 = CanonicalDocument(
            source=Source.ROSARIO,
            doc_type=DocumentType.ORDENANZA,
            number="10",
            year=2023,
            subject=None,
            sanction_date=None,
            publication_date=None,
            source_url="https://example.com",
            content_path=None,
            content_format=None,
        )
        doc2 = CanonicalDocument(
            source=Source.ROSARIO,
            doc_type=DocumentType.ORDENANZA,
            number="10",
            year=2023,
            subject=None,
            sanction_date=None,
            publication_date=None,
            source_url="https://example.com",
            content_path=None,
            content_format=None,
        )
        assert doc1 == doc2

    def test_docs_with_different_source_not_equal(self) -> None:
        base = {
            "doc_type": DocumentType.DECRETO,
            "number": None,
            "year": None,
            "subject": None,
            "sanction_date": None,
            "publication_date": None,
            "source_url": "https://example.com",
            "content_path": None,
            "content_format": None,
        }
        doc_r = CanonicalDocument(source=Source.ROSARIO, **base)
        doc_sf = CanonicalDocument(source=Source.SANTA_FE, **base)
        assert doc_r != doc_sf
