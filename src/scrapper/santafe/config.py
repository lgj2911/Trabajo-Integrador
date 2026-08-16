"""Configuration for the Municipalidad de Santa Fe scraper.

Source: https://transparencia.santafeciudad.gov.ar

Resolution strategy (per document page enumerated from the XML sitemaps):
    PDF found at /wp-content/uploads/ -> download the file
    No PDF (older / text-only docs)  -> extract inline body text, save as .txt
"""

from __future__ import annotations

from pathlib import Path

BASE_URL = "https://transparencia.santafeciudad.gov.ar"
SITEMAP_INDEX_URL = f"{BASE_URL}/sitemap_index.xml"
LOG_FILE = "downloader_santa_fe.log"

# __file__ is undefined in Jupyter/Colab; fall back to cwd.
try:
    _SCRAPPER_ROOT = Path(__file__).resolve().parent.parent
except NameError:
    _SCRAPPER_ROOT = Path.cwd()

CHECKPOINT_FILE = _SCRAPPER_ROOT / "checkpoint_santa_fe.json"

ALL_COLLECTIONS = ("normativa", "compra", "contratacion", "convocatorias")

# Ordered longest-first so more specific prefixes match before shorter ones.
_NORMATIVA_TYPE_PATTERNS: list[tuple[str, str]] = [
    ("resolucion-conjunta-", "resolucion_conjunta"),
    ("resolucion-dem-", "resolucion_dem"),
    ("resolucion-hcm-", "resolucion_hcm"),
    ("decreto-dmm-", "decreto_dmm"),
    ("decreto-dpb-", "decreto_dpb"),
    ("ordenanza-", "ordenanza"),
]

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
