"""Configuration for the Municipalidad de Rosario scraper.

Link types resolved by this scraper:
    direct_pdf   -- URL already points to the PDF (newer boletines)
    boletin_html -- HTML page with an index of internal PDFs (boletines IDs 2-218)
    normativa    -- visualExterna.do?idNormativa=X -> direct verArchivo URL
    html_to_pdf  -- Plone /mr/normativa/ page -> converted with weasyprint
    scrape_page  -- generic scraping (compendios)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict

BASE_URL = "https://www.rosario.gob.ar"
LOG_FILE = "downloader.log"

# __file__ is undefined in Jupyter/Colab; fall back to cwd.
try:
    _SCRAPPER_ROOT = Path(__file__).resolve().parent.parent
except NameError:
    _SCRAPPER_ROOT = Path.cwd()

# Folder holding the CSVs; overridable via the SCRAPPER_DIR env var or --csv-dir.
SCRAPPER_DIR = Path(os.environ.get("SCRAPPER_DIR", str(_SCRAPPER_ROOT)))
CHECKPOINT_FILE = _SCRAPPER_ROOT / "checkpoint.json"


class CsvConfig(TypedDict):
    """Per-CSV settings driving how tasks are built for one Rosario document type."""

    folder: str
    link_col: str
    link_type: str
    name_cols: list[str]
    name_fmt: str


CSV_CONFIG: dict[str, CsvConfig] = {
    "boletines.csv": {
        "folder": "boletines",
        "link_col": "LINK",
        "link_type": "direct_pdf",  # URL already points directly to the PDF
        "name_cols": ["NUMERO", "ANIO"],
        "name_fmt": "boletin_{NUMERO}_{ANIO}.pdf",
    },
    "compendios_de_boletines.csv": {
        "folder": "compendios_de_boletines",
        "link_col": "LINK",
        "link_type": "scrape_page",  # page with iframe/embed of the PDF
        "name_cols": ["COMPENDIO", "PERIODO"],
        "name_fmt": "{COMPENDIO}_{PERIODO}.pdf",
    },
    "convenios.csv": {
        "folder": "convenios",
        "link_col": "TEXTO_VIGENTE_NORMA",
        "link_type": "normativa",  # visualExterna.do -> scraping for real PDF
        "name_cols": ["NUMERO", "ANIO"],
        "name_fmt": "convenio_{NUMERO}_{ANIO}.pdf",
    },
    "declaraciones_concejo_municipal.csv": {
        "folder": "declaraciones_concejo_municipal",
        "link_col": "TEXTO_VIGENTE_NORMA",
        "link_type": "normativa",
        "name_cols": ["NUMERO", "ANIO"],
        "name_fmt": "declaracion_{NUMERO}_{ANIO}.pdf",
    },
    "decreto_ordenanzas.csv": {
        "folder": "decreto_ordenanzas",
        "link_col": "TEXTO_VIGENTE_NORMA",
        "link_type": "normativa",
        "name_cols": ["NUMERO", "ANIO"],
        "name_fmt": "decreto_ordenanza_{NUMERO}_{ANIO}.pdf",
    },
    "decretos.csv": {
        "folder": "decretos",
        "link_col": "TEXTO_VIGENTE_NORMA",
        "link_type": "normativa",
        "name_cols": ["NUMERO", "ANIO"],
        "name_fmt": "decreto_{NUMERO}_{ANIO}.pdf",
    },
    "decretos_concejo_municipal.csv": {
        "folder": "decretos_concejo_municipal",
        "link_col": "TEXTO_VIGENTE_NORMA",
        "link_type": "normativa",
        "name_cols": ["NUMERO", "ANIO"],
        "name_fmt": "decreto_cm_{NUMERO}_{ANIO}.pdf",
    },
    "ordenanzas.csv": {
        "folder": "ordenanzas",
        "link_col": "TEXTO_VIGENTE_NORMA",
        "link_type": "normativa",
        "name_cols": ["NUMERO", "ANIO"],
        "name_fmt": "ordenanza_{NUMERO}_{ANIO}.pdf",
    },
    "resoluciones.csv": {
        "folder": "resoluciones",
        "link_col": "TEXTO_VIGENTE_NORMA",
        "link_type": "normativa",
        "name_cols": ["NUMERO", "ANIO"],
        "name_fmt": "resolucion_{NUMERO}_{ANIO}.pdf",
    },
    "resoluciones_concejo_municipal.csv": {
        "folder": "resoluciones_concejo_municipal",
        "link_col": "TEXTO_VIGENTE_NORMA",
        "link_type": "normativa",
        "name_cols": ["NUMERO", "ANIO"],
        "name_fmt": "resolucion_cm_{NUMERO}_{ANIO}.pdf",
    },
}
