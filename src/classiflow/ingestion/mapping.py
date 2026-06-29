"""Adapters that map each source's native records into `CanonicalDocument`.

Rosario records arrive as CSV rows (one CSV per document type, see
scrapper/downloader.py:CSV_CONFIG). Santa Fe records arrive as page URLs
whose document type is inferred from the slug (see
scrapper/downloader_santa_fe.py:_NORMATIVA_TYPE_PATTERNS) — the portal page
itself also carries secretariat, expedient and signatory metadata, but the
current downloader does not parse it out yet, so those fields stay empty
here until that extraction is added.
"""

from __future__ import annotations

from datetime import date
from urllib.parse import urlparse

from classiflow.ingestion.schema import CanonicalDocument, ContentFormat, DocumentType, Source

# ──────────────────────────────────────────────────────────────
# Rosario: CSV filename → canonical document type
# ──────────────────────────────────────────────────────────────

ROSARIO_DOC_TYPE_BY_CSV: dict[str, DocumentType] = {
    "boletines.csv": DocumentType.BOLETIN,
    "compendios_de_boletines.csv": DocumentType.COMPENDIO_BOLETINES,
    "convenios.csv": DocumentType.CONVENIO,
    "declaraciones_concejo_municipal.csv": DocumentType.DECLARACION,
    "decreto_ordenanzas.csv": DocumentType.DECRETO_ORDENANZA,
    "decretos.csv": DocumentType.DECRETO,
    "decretos_concejo_municipal.csv": DocumentType.DECRETO_CONCEJO,
    "ordenanzas.csv": DocumentType.ORDENANZA,
    "resoluciones.csv": DocumentType.RESOLUCION,
    "resoluciones_concejo_municipal.csv": DocumentType.RESOLUCION_CONCEJO,
}

# Rosario CSV columns that have no canonical field but are worth keeping.
_ROSARIO_RAW_FIELDS = ("NRO_BOLETIN", "ANIO_BOLETIN", "FUE_ACTUALIZADA")


def _parse_rosario_date(value: str | None) -> date | None:
    """Parse a Rosario CSV date such as '14/05/2026'.

    Returns:
        The parsed date, or None if `value` is empty or malformed.
    """
    if not value:
        return None
    try:
        day_str, month_str, year_str = value.split("/")
        return date(int(year_str), int(month_str), int(day_str))
    except ValueError:
        return None


def map_rosario_row(
    row: dict[str, str],
    csv_filename: str,
    content_path: str | None,
) -> CanonicalDocument:
    """Map a Rosario CSV row into a `CanonicalDocument`.

    Returns:
        The canonical document built from `row`.
    """
    doc_type = ROSARIO_DOC_TYPE_BY_CSV.get(csv_filename, DocumentType.OTRO)
    year_str = row.get("ANIO", "")
    return CanonicalDocument(
        source=Source.ROSARIO,
        doc_type=doc_type,
        number=row.get("NUMERO") or None,
        year=int(year_str) if year_str.isdigit() else None,
        subject=row.get("ASUNTO") or None,
        sanction_date=_parse_rosario_date(row.get("FEC_SANCION")),
        publication_date=_parse_rosario_date(row.get("FEC_PUBLICACION_BOLETIN")),
        source_url=row.get("TEXTO_VIGENTE_NORMA") or row.get("LINK") or "",
        content_path=content_path,
        content_format=ContentFormat.PDF if content_path else None,
        raw_metadata={field: row.get(field) for field in _ROSARIO_RAW_FIELDS if field in row},
    )


# ──────────────────────────────────────────────────────────────
# Santa Fe: slug prefix / collection → canonical document type
# ──────────────────────────────────────────────────────────────

SANTA_FE_NORMATIVA_TYPE_BY_SLUG_PREFIX: tuple[tuple[str, DocumentType], ...] = (
    ("resolucion-conjunta-", DocumentType.RESOLUCION_CONJUNTA),
    ("resolucion-dem-", DocumentType.RESOLUCION),
    ("resolucion-hcm-", DocumentType.RESOLUCION_CONCEJO),
    ("decreto-dmm-", DocumentType.DECRETO),
    ("decreto-dpb-", DocumentType.DECRETO),
    ("ordenanza-", DocumentType.ORDENANZA),
)

SANTA_FE_DOC_TYPE_BY_COLLECTION: dict[str, DocumentType] = {
    "compras-y-contrataciones": DocumentType.COMPRA,
    "contratacion-obra": DocumentType.CONTRATACION,
    "convocatoria": DocumentType.CONVOCATORIA,
    "convocatorias-anteriores": DocumentType.CONVOCATORIA,
}


def _santa_fe_collection(url: str) -> str:
    parts = urlparse(url).path.strip("/").split("/")
    return parts[0] if parts else "unknown"


def _santa_fe_doc_type(url: str) -> DocumentType:
    collection = _santa_fe_collection(url)
    if collection != "normativa":
        return SANTA_FE_DOC_TYPE_BY_COLLECTION.get(collection, DocumentType.OTRO)
    slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    for prefix, doc_type in SANTA_FE_NORMATIVA_TYPE_BY_SLUG_PREFIX:
        if slug.startswith(prefix):
            return doc_type
    return DocumentType.OTRO


def map_santa_fe_document(
    url: str,
    content_path: str | None,
    content_format: ContentFormat | None,
) -> CanonicalDocument:
    """Map a Santa Fe portal page into a `CanonicalDocument`.

    `number`, `year`, `subject` and the date fields are left empty: the
    downloader only resolves the PDF/text body today, it does not yet parse
    the per-page metadata block (year, secretariat, expedient, signatories).

    Returns:
        The canonical document built from the page at `url`.
    """
    return CanonicalDocument(
        source=Source.SANTA_FE,
        doc_type=_santa_fe_doc_type(url),
        number=None,
        year=None,
        subject=None,
        sanction_date=None,
        publication_date=None,
        source_url=url,
        content_path=content_path,
        content_format=content_format,
        raw_metadata={},
    )
