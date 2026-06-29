"""
Bulk document downloader — Municipalidad de Santa Fe
Downloads normativas, procurement docs, and public calls from the transparency portal.
Source: https://transparencia.santafeciudad.gov.ar

CLI usage:
    python downloader_santa_fe.py [--output ./downloads_santa_fe] [--concurrency 5]
                                  [--delay 0.5] [--checkpoint ./checkpoint_santa_fe.json]
                                  [--collections normativa compra contratacion convocatorias]

Google Colab usage:
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location("sf", "/path/to/downloader_santa_fe.py")
    mod = importlib.util.load_from_spec(spec); spec.loader.exec_module(mod)
    await mod.run_colab(
        output="/content/drive/MyDrive/downloads_santa_fe", concurrency=3, delay=1.0
    )

Resolution strategy (html_scrape_normativa):
    1. Enumerate URLs from XML sitemaps (normativa-sitemap*.xml, compra-sitemap*.xml, etc.)
    2. For each page:
         - PDF found at /wp-content/uploads/ → download the file
         - No PDF (older / text-only docs)  → extract inline body text and save as .txt
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET  # noqa: S405

import aiofiles
import aiohttp
from bs4 import BeautifulSoup
from tqdm.asyncio import tqdm

# ──────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────

BASE_URL = "https://transparencia.santafeciudad.gov.ar"
SITEMAP_INDEX_URL = f"{BASE_URL}/sitemap_index.xml"

HTTP_OK = 200
HTTP_NOT_FOUND = 404

# __file__ is undefined in Jupyter/Colab; fall back to cwd
try:
    _THIS_DIR = Path(__file__).parent
except NameError:
    _THIS_DIR = Path.cwd()

CHECKPOINT_FILE = _THIS_DIR / "checkpoint_santa_fe.json"

ALL_COLLECTIONS = ("normativa", "compra", "contratacion", "convocatorias")

# Ordered longest-first so more specific prefixes match before shorter ones
_NORMATIVA_TYPE_PATTERNS: list[tuple[str, str]] = [
    ("resolucion-conjunta-", "resolucion_conjunta"),
    ("resolucion-dem-", "resolucion_dem"),
    ("resolucion-hcm-", "resolucion_hcm"),
    ("decreto-dmm-", "decreto_dmm"),
    ("decreto-dpb-", "decreto_dpb"),
    ("ordenanza-", "ordenanza"),
]

# Real browser User-Agent to avoid being blocked
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9",
}

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _build_handlers() -> list[logging.Handler]:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    with contextlib.suppress(OSError):
        handlers.insert(0, logging.FileHandler("downloader_santa_fe.log", encoding="utf-8"))
    return handlers


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=_build_handlers(),
)
log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# URL / path utilities
# ──────────────────────────────────────────────────────────────


def _slug_from_url(url: str) -> str:
    return urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]


def _collection_from_url(url: str) -> str:
    parts = urlparse(url).path.strip("/").split("/")
    return parts[0] if parts else "unknown"


def _normativa_type(slug: str) -> str:
    for prefix, folder in _NORMATIVA_TYPE_PATTERNS:
        if slug.startswith(prefix):
            return folder
    return "otros"


def _dest_folder(output_dir: Path, url: str) -> Path:
    collection = _collection_from_url(url)
    slug = _slug_from_url(url)
    if collection == "normativa":
        return output_dir / collection / _normativa_type(slug)
    return output_dir / collection


def _sitemap_matches(sitemap_url: str, collections: tuple[str, ...]) -> bool:
    filename = urlparse(sitemap_url).path.rsplit("/", 1)[-1]
    return any(filename.startswith(f"{c}-sitemap") for c in collections)


# ──────────────────────────────────────────────────────────────
# HTML extraction
# ──────────────────────────────────────────────────────────────


def extract_wp_pdf_url(html: str, page_url: str) -> str | None:
    """Find a /wp-content/uploads/*.pdf link in the page.

    Scans all tag attributes since the PDF anchor may not be in the main content area.

    Returns:
        Absolute PDF URL if found, else None.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all(name=True):
        for attr in ("href", "src", "data"):
            val = tag.get(attr, "")
            if (
                isinstance(val, str)
                and "/wp-content/uploads/" in val
                and val.lower().endswith(".pdf")
            ):
                return val if val.startswith("http") else urljoin(page_url, val)
    return None


def extract_body_text(html: str) -> str:
    """Extract the main text content from a WordPress normativa page.

    Tries common WordPress content selectors before falling back to the full body.

    Returns:
        Cleaned plain text from the document body.
    """
    soup = BeautifulSoup(html, "lxml")
    for selector in ("div.entry-content", "div.post-content", "article", "div.content", "main"):
        node = soup.select_one(selector)
        if node:
            return node.get_text(separator="\n", strip=True)
    for tag in soup.find_all(["nav", "header", "footer", "script", "style"]):
        tag.decompose()
    body = soup.find("body")
    return (
        body.get_text(separator="\n", strip=True)
        if body
        else soup.get_text(separator="\n", strip=True)
    )


# ──────────────────────────────────────────────────────────────
# Checkpoint
# ──────────────────────────────────────────────────────────────
# The set stores two entry types:
#   "https://...slug/"         → successfully downloaded or saved
#   "SKIP:https://...slug/"    → permanent failure, do not retry

SKIP_PREFIX = "SKIP:"


def load_checkpoint(path: Path | None = None) -> set[str]:
    """Load the set of checkpoint keys from disk.

    Returns:
        Set of URL keys for completed and permanently-skipped items.
    """
    ckpt = path or CHECKPOINT_FILE
    if ckpt.exists():
        with ckpt.open(encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_checkpoint(done: set[str], path: Path | None = None) -> None:
    ckpt = path or CHECKPOINT_FILE
    with ckpt.open("w", encoding="utf-8") as f:
        json.dump(list(done), f)


def is_pending(key: str, done: set[str]) -> bool:
    """Check whether an item still needs to be processed.

    Returns:
        True if the key is absent from the checkpoint (neither completed nor permanently skipped).
    """
    return key not in done and (SKIP_PREFIX + key) not in done


# ──────────────────────────────────────────────────────────────
# Sitemap enumeration
# ──────────────────────────────────────────────────────────────


async def _fetch_xml(session: aiohttp.ClientSession, url: str) -> str | None:
    try:
        async with session.get(
            url,
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            if resp.status != HTTP_OK:
                log.warning("HTTP %d fetching: %s", resp.status, url)
                return None
            return await resp.text(errors="replace")
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        log.warning("Error fetching %s: %s", url, exc)
        return None


def _parse_sitemap_locs(xml_text: str) -> list[str]:
    try:
        root = ET.fromstring(xml_text)  # noqa: S314
    except ET.ParseError as exc:
        log.warning("Failed to parse sitemap XML: %s", exc)
        return []
    locs = [el.text for el in root.findall(".//sm:loc", _SITEMAP_NS) if el.text]
    if not locs:
        locs = [el.text for el in root.findall(".//loc") if el.text]
    return locs


async def fetch_sitemap_urls(session: aiohttp.ClientSession, sitemap_url: str) -> list[str]:
    """Fetch a sitemap and return all document URLs found in it.

    Returns:
        List of <loc> URL strings.
    """
    xml_text = await _fetch_xml(session, sitemap_url)
    return _parse_sitemap_locs(xml_text) if xml_text else []


async def enumerate_all_urls(
    session: aiohttp.ClientSession,
    collections: tuple[str, ...] = ALL_COLLECTIONS,
) -> list[str]:
    """Parse the sitemap index and collect all document URLs for the given collections.

    Returns:
        Deduplicated list of document page URLs across all matched sitemaps.
    """
    log.info("Fetching sitemap index: %s", SITEMAP_INDEX_URL)
    index_locs = await fetch_sitemap_urls(session, SITEMAP_INDEX_URL)
    if not index_locs:
        log.error("Sitemap index returned no entries")
        return []

    sitemap_urls = [u for u in index_locs if _sitemap_matches(u, collections)]
    log.info(
        "Found %d sitemaps for collections: %s",
        len(sitemap_urls),
        ", ".join(collections),
    )

    all_urls: list[str] = []
    for sitemap_url in sitemap_urls:
        urls = await fetch_sitemap_urls(session, sitemap_url)
        log.info("  %s → %d URLs", sitemap_url.rsplit("/", 1)[-1], len(urls))
        all_urls.extend(urls)

    seen: set[str] = set()
    unique: list[str] = []
    for url in all_urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)

    log.info("Total unique document URLs: %d", len(unique))
    return unique


# ──────────────────────────────────────────────────────────────
# File download / text save
# ──────────────────────────────────────────────────────────────


async def _fetch_pdf_bytes(
    session: aiohttp.ClientSession,
    pdf_url: str,
) -> tuple[bool | str, bytes | None]:
    async with session.get(
        pdf_url,
        headers={**HEADERS, "Accept": "application/pdf,*/*"},
        timeout=aiohttp.ClientTimeout(total=90),
        allow_redirects=True,
    ) as resp:
        if resp.status == HTTP_NOT_FOUND:
            log.warning("404 PDF not available: %s", pdf_url)
            return "PERMANENT", None
        if resp.status != HTTP_OK:
            log.warning("HTTP %d downloading PDF: %s", resp.status, pdf_url)
            return "RETRY", None
        data = await resp.read()
        if not data or b"%PDF" not in data[:10]:
            log.warning("Response is not a valid PDF (%d bytes) — skipping: %s", len(data), pdf_url)
            return "PERMANENT", None
        return True, data


async def download_pdf(
    session: aiohttp.ClientSession,
    pdf_url: str,
    dest: Path,
    delay: float,
    retries: int = 3,
) -> bool | str:
    """Download a PDF from *pdf_url* and write it to *dest*.

    Returns:
        True on success, "PERMANENT" for definitively bad responses,
        False for transient failures that should be retried next run.
    """
    await asyncio.sleep(delay)
    for attempt in range(1, retries + 1):
        try:
            result, data = await _fetch_pdf_bytes(session, pdf_url)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.warning("Error on attempt %d/%d (%s): %s", attempt, retries, pdf_url, exc)
            await asyncio.sleep(2**attempt)
            continue

        if result == "RETRY":
            await asyncio.sleep(2**attempt)
            continue
        if result is not True:
            return result  # type: ignore[return-value]  # "PERMANENT" or False

        assert data is not None
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(dest, "wb") as f:
            await f.write(data)
        return True

    log.error("Permanent network failure after %d attempts: %s", retries, pdf_url)
    return False


async def save_text(text: str, dest: Path) -> None:
    """Write extracted plain text to *dest*."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(dest, "w", encoding="utf-8") as f:
        await f.write(text)


# ──────────────────────────────────────────────────────────────
# Task list
# ──────────────────────────────────────────────────────────────


def build_task_list(output_dir: Path, urls: list[str]) -> list[dict]:
    """Build a download task list from enumerated document page URLs.

    Returns:
        List of task dicts with: key (URL), page_url, slug, dest_folder.
    """
    return [
        {
            "key": url,
            "page_url": url,
            "slug": _slug_from_url(url),
            "dest_folder": _dest_folder(output_dir, url),
        }
        for url in urls
    ]


# ──────────────────────────────────────────────────────────────
# Orchestrator helpers
# ──────────────────────────────────────────────────────────────


@dataclass
class _DownloadCtx:
    session: aiohttp.ClientSession
    semaphore: asyncio.Semaphore
    delay: float
    checkpoint_file: Path | None = None


async def _fetch_page_html(
    session: aiohttp.ClientSession,
    url: str,
) -> tuple[int, str, str]:
    async with session.get(
        url,
        headers=HEADERS,
        timeout=aiohttp.ClientTimeout(total=30),
        allow_redirects=True,
    ) as resp:
        html = await resp.text(errors="replace") if resp.status == HTTP_OK else ""
        return resp.status, html, str(resp.url)


async def _process_task(
    ctx: _DownloadCtx,
    task: dict,
    done: set[str],
    stats: dict[str, int],
) -> None:
    """Fetch a document page, download the PDF if present, or save the extracted text."""
    async with ctx.semaphore:
        await asyncio.sleep(ctx.delay)
        try:
            status, html, page_url = await _fetch_page_html(ctx.session, task["page_url"])
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.warning("Error fetching %s: %s", task["page_url"], exc)
            stats["transient"] += 1
            return

        if status == HTTP_NOT_FOUND:
            log.info("Page not found (404): %s", task["page_url"])
            done.add(SKIP_PREFIX + task["key"])
            stats["permanent"] += 1
            return
        if status != HTTP_OK:
            log.warning("HTTP %d fetching page: %s", status, task["page_url"])
            stats["transient"] += 1
            return

        pdf_url = extract_wp_pdf_url(html, page_url)
        if pdf_url:
            dest = task["dest_folder"] / f"{task['slug']}.pdf"
            result = await download_pdf(ctx.session, pdf_url, dest, ctx.delay)
            if result is True:
                done.add(task["key"])
                stats["ok_pdf"] += 1
            elif result == "PERMANENT":
                done.add(SKIP_PREFIX + task["key"])
                stats["permanent"] += 1
            else:
                stats["transient"] += 1
        else:
            text = extract_body_text(html)
            if not text.strip():
                log.info("Empty page body, permanently skipping: %s", task["page_url"])
                done.add(SKIP_PREFIX + task["key"])
                stats["permanent"] += 1
                return
            dest = task["dest_folder"] / f"{task['slug']}.txt"
            await save_text(text, dest)
            done.add(task["key"])
            stats["ok_text"] += 1

        total_ok = stats["ok_pdf"] + stats["ok_text"]
        if total_ok > 0 and total_ok % 50 == 0:
            save_checkpoint(done, ctx.checkpoint_file)
            log.info(
                "Checkpoint: %d PDF + %d text saved",
                stats["ok_pdf"],
                stats["ok_text"],
            )


# ──────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────


async def run(
    output_dir: Path,
    concurrency: int,
    delay: float,
    collections: tuple[str, ...] = ALL_COLLECTIONS,
    checkpoint_file: Path | None = None,
) -> None:
    done = load_checkpoint(checkpoint_file)
    connector = aiohttp.TCPConnector(limit=concurrency, ssl=False)
    stats: dict[str, int] = {"ok_pdf": 0, "ok_text": 0, "permanent": 0, "transient": 0}

    async with aiohttp.ClientSession(connector=connector) as session:
        urls = await enumerate_all_urls(session, collections)
        tasks = build_task_list(output_dir, urls)
        pending = [t for t in tasks if is_pending(t["key"], done)]

        skipped = sum(1 for t in tasks if (SKIP_PREFIX + t["key"]) in done)
        ok_prev = sum(1 for t in tasks if t["key"] in done)
        log.info(
            "Total: %d | Previously OK: %d | Skipped: %d | Pending: %d",
            len(tasks),
            ok_prev,
            skipped,
            len(pending),
        )

        ctx = _DownloadCtx(
            session=session,
            semaphore=asyncio.Semaphore(concurrency),
            delay=delay,
            checkpoint_file=checkpoint_file,
        )
        await tqdm.gather(
            *[_process_task(ctx, t, done, stats) for t in pending],
            desc="Downloading",
            total=len(pending),
        )

    save_checkpoint(done, checkpoint_file)
    log.info(
        "Done. PDF: %d | Text: %d | No content/permanent: %d | Network error (retryable): %d",
        stats["ok_pdf"],
        stats["ok_text"],
        stats["permanent"],
        stats["transient"],
    )


# ──────────────────────────────────────────────────────────────
# Entry points
# ──────────────────────────────────────────────────────────────


async def run_colab(
    output: str = "./downloads_santa_fe",
    concurrency: int = 3,
    delay: float = 1.0,
    collections: tuple[str, ...] = ALL_COLLECTIONS,
    checkpoint: str | None = None,
) -> None:
    """Async entry point for Google Colab notebooks.

    Call with ``await run_colab(...)`` in a notebook cell.

    Args:
        output:      Destination folder for downloaded files.
        concurrency: Parallel downloads — keep ≤ 3 in Colab to avoid rate-limiting.
        delay:       Seconds between requests.
        collections: Which collections to scrape (default: all four).
        checkpoint:  Path to the checkpoint JSON file.
                     Defaults to checkpoint_santa_fe.json next to this script.
    """
    output_dir = Path(output).resolve()  # noqa: ASYNC240
    output_dir.mkdir(exist_ok=True, parents=True)
    ckpt = Path(checkpoint) if checkpoint else None
    log.info("Output: %s | Concurrency: %d | Delay: %.1fs", output_dir, concurrency, delay)
    log.info("Collections: %s", ", ".join(collections))
    await run(output_dir, concurrency, delay, collections=collections, checkpoint_file=ckpt)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bulk downloader — Municipalidad de Santa Fe transparency portal"
    )
    parser.add_argument("--output", default="./downloads_santa_fe")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Parallel downloads (default: 5 — keep low to avoid being blocked)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Seconds to wait between requests (default: 0.5)",
    )
    parser.add_argument(
        "--collections",
        nargs="+",
        default=list(ALL_COLLECTIONS),
        choices=list(ALL_COLLECTIONS),
        metavar="COLLECTION",
        help=f"Collections to scrape (default: all). Choices: {', '.join(ALL_COLLECTIONS)}",
    )
    parser.add_argument(
        "--checkpoint",
        default=None,
        help="Path to checkpoint JSON file (default: checkpoint_santa_fe.json next to this script)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_file = Path(args.checkpoint) if args.checkpoint else None
    collections = tuple(args.collections)

    log.info(
        "Output: %s | Concurrency: %d | Delay: %.1fs",
        output_dir,
        args.concurrency,
        args.delay,
    )
    log.info("Collections: %s", ", ".join(collections))

    asyncio.run(
        run(
            output_dir,
            args.concurrency,
            args.delay,
            collections=collections,
            checkpoint_file=checkpoint_file,
        )
    )


if __name__ == "__main__":
    main()
