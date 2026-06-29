"""Canonical document schema shared by every ingestion source."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date


class Source(str, Enum):
    """Origin system a document was ingested from."""

    ROSARIO = "rosario"
    SANTA_FE = "santa_fe"


class ContentFormat(str, Enum):
    """Storage format of the document body."""

    PDF = "pdf"
    HTML_TEXT = "html_text"


class DocumentType(str, Enum):
    """Document type, normalized across municipalities.

    Rosario and Santa Fe use different names for similar acts (e.g. Santa Fe's
    "Resolución HCM" is the council-level resolution Rosario calls
    "resolucion_concejo"). Values here are the shared vocabulary both sources
    map into.
    """

    DECRETO = "decreto"
    DECRETO_CONCEJO = "decreto_concejo"
    ORDENANZA = "ordenanza"
    DECRETO_ORDENANZA = "decreto_ordenanza"
    RESOLUCION = "resolucion"
    RESOLUCION_CONCEJO = "resolucion_concejo"
    RESOLUCION_CONJUNTA = "resolucion_conjunta"
    CONVENIO = "convenio"
    DECLARACION = "declaracion"
    BOLETIN = "boletin"
    COMPENDIO_BOLETINES = "compendio_boletines"
    COMPRA = "compra"
    CONTRATACION = "contratacion"
    CONVOCATORIA = "convocatoria"
    OTRO = "otro"


@dataclass(frozen=True, slots=True)
class CanonicalDocument:
    """Unified representation of a municipal document, regardless of source.

    `raw_metadata` preserves source-specific fields that have no canonical
    equivalent (e.g. Rosario's NRO_BOLETIN, Santa Fe's signatories) so they
    are not lost when adapting into this schema.
    """

    source: Source
    doc_type: DocumentType
    number: str | None
    year: int | None
    subject: str | None
    sanction_date: date | None
    publication_date: date | None
    source_url: str
    content_path: str | None
    content_format: ContentFormat | None
    raw_metadata: dict[str, str | None] = field(default_factory=dict)
