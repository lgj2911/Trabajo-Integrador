"""Build the Rosario download task list from the open-data CSVs."""

from __future__ import annotations

import asyncio
import csv
import logging
import re
from pathlib import Path
from typing import TypedDict

import aiohttp

from scrapper.common.config import HEADERS, HTTP_OK
from scrapper.common.urls import normalize_url
from scrapper.rosario.config import BASE_URL, CSV_CONFIG, SCRAPPER_DIR

log = logging.getLogger(__name__)


class RosarioTask(TypedDict):
    """A single download task for the Rosario scraper."""

    key: str
    page_url: str
    link_type: str
    dest: Path
    folder: Path
    name_base: str


def sanitize(text: str) -> str:
    """Replace filesystem-unsafe characters in *text* with underscores.

    Returns:
        A filename-safe version of *text*.
    """
    return re.sub(r'[\\/*?:"<>|]', "_", text).strip()


def _resolve_csv_path(csv_dir: Path, csv_file: str) -> Path | None:
    """Find *csv_file* in *csv_dir*, falling back to a case-insensitive name match.

    Returns:
        Resolved Path if found, else None.
    """
    exact = csv_dir / csv_file
    if exact.exists():
        return exact

    def _normalize(name: str) -> str:
        return re.sub(r"[\s\-]+", "_", name).lower()

    target = _normalize(csv_file)
    for candidate in csv_dir.iterdir():
        if candidate.suffix.lower() == ".csv" and _normalize(candidate.name) == target:
            return candidate
    return None


def build_task_list(output_dir: Path, csv_dir: Path | None = None) -> list[RosarioTask]:
    """Build the full download task list from every configured CSV.

    Returns:
        List of task dicts (key, page_url, link_type, dest, folder, name_base).
    """
    src_dir = csv_dir if csv_dir is not None else SCRAPPER_DIR
    tasks: list[RosarioTask] = []
    for csv_file, cfg in CSV_CONFIG.items():
        csv_path = _resolve_csv_path(src_dir, csv_file)
        if csv_path is None:
            log.warning("CSV not found: %s", src_dir / csv_file)
            continue

        folder = output_dir / cfg["folder"]
        with Path(csv_path).open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                link = row.get(cfg["link_col"], "").strip().strip('"')
                if not link:
                    continue

                name_parts = {k: sanitize(row.get(k, "").strip()) for k in cfg["name_cols"]}
                filename = cfg["name_fmt"].format(**name_parts)
                dest = folder / filename

                # Detect special link types from the URL content.
                link_type = cfg["link_type"]
                if "boletin.do?accion=ver2" in link or ("boletin.do" in link and "ver2" in link):
                    link_type = "boletin_html"
                elif "/mr/normativa/" in link:
                    link_type = "html_to_pdf"

                tasks.append({
                    "key": str(dest),
                    "page_url": link,
                    "link_type": link_type,
                    "dest": dest,
                    # extra data for naming sub-files in boletin_html
                    "folder": folder,
                    "name_base": filename.replace(".pdf", ""),
                })

    return tasks


async def expand_boletin_tasks(
    session: aiohttp.ClientSession,
    boletin_tasks: list[RosarioTask],
    delay: float,
) -> list[RosarioTask]:
    """Expand HTML boletines into one download task per internal PDF.

    For each HTML boletin (boletin.do?accion=ver2), scrapes the page, extracts
    the internal PDF IDs via ver(id) in the JS, and returns one individual task
    per PDF found.

    Returns:
        List of download task dicts, one per internal PDF discovered across all
        boletines.
    """
    expanded: list[RosarioTask] = []
    for task in boletin_tasks:
        url = normalize_url(task["page_url"])
        if not url:
            continue
        await asyncio.sleep(delay)
        try:
            async with session.get(
                url,
                headers=HEADERS,
                timeout=aiohttp.ClientTimeout(total=20),
                allow_redirects=True,
            ) as resp:
                if resp.status != HTTP_OK:
                    log.warning("HTTP %d expanding boletin: %s", resp.status, url)
                    continue
                html = await resp.text(errors="replace")
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.warning("Error expanding boletin %s: %s", url, exc)
            continue

        pdf_ids = re.findall(r"\bver\((\d+)\)", html)
        if not pdf_ids:
            log.info("Boletin with no internal PDFs: %s", url)
            continue

        log.info("Boletin %s -> %d internal PDFs", task["page_url"], len(pdf_ids))
        for pdf_id in pdf_ids:
            pdf_url = f"{BASE_URL}/normativa/verArchivo?tipo=pdf&id={pdf_id}&modo=attachment"
            dest = task["folder"] / f"{task['name_base']}_doc_{pdf_id}.pdf"
            expanded.append({
                "key": str(dest),
                "page_url": pdf_url,
                "link_type": "direct_pdf",
                "dest": dest,
                "folder": task["folder"],
                "name_base": task["name_base"],
            })

    return expanded
