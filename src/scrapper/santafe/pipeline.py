"""Orchestrator for the Municipalidad de Santa Fe scraper."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import aiohttp
from tqdm.asyncio import tqdm

from scrapper.common.checkpoint import (
    SKIP_PREFIX,
    is_pending,
    load_checkpoint,
    save_checkpoint,
)
from scrapper.common.config import HEADERS, HTTP_NOT_FOUND, HTTP_OK
from scrapper.common.downloader import DownloadCtx, download_pdf, save_text
from scrapper.common.logging_setup import configure_logging
from scrapper.santafe.config import ALL_COLLECTIONS, CHECKPOINT_FILE, LOG_FILE
from scrapper.santafe.extract import extract_body_text, extract_wp_pdf_url
from scrapper.santafe.sitemap import enumerate_all_urls
from scrapper.santafe.tasks import SantaFeTask, build_task_list

log = logging.getLogger(__name__)


async def _fetch_page_html(
    session: aiohttp.ClientSession,
    url: str,
) -> tuple[int, str, str]:
    """Fetch an HTML document page.

    Returns:
        (status, html, final_url); html is empty when status != 200.
    """
    async with session.get(
        url,
        headers=HEADERS,
        timeout=aiohttp.ClientTimeout(total=30),
        allow_redirects=True,
    ) as resp:
        html = await resp.text(errors="replace") if resp.status == HTTP_OK else ""
        return resp.status, html, str(resp.url)


async def _process_task(
    ctx: DownloadCtx,
    task: SantaFeTask,
    done: set[str],
    stats: dict[str, int],
) -> None:
    """Fetch a document page, download the PDF if present, or save the text."""
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
        if total_ok > 0 and total_ok % 50 == 0 and ctx.checkpoint_file is not None:
            save_checkpoint(done, ctx.checkpoint_file)
            log.info(
                "Checkpoint: %d PDF + %d text saved",
                stats["ok_pdf"],
                stats["ok_text"],
            )


async def run(
    output_dir: Path,
    concurrency: int,
    delay: float,
    collections: tuple[str, ...] = ALL_COLLECTIONS,
    checkpoint_file: Path | None = None,
) -> None:
    """Run the full Santa Fe download pipeline."""
    ckpt = checkpoint_file or CHECKPOINT_FILE
    done = load_checkpoint(ckpt)
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

        ctx = DownloadCtx(
            session=session,
            semaphore=asyncio.Semaphore(concurrency),
            delay=delay,
            checkpoint_file=ckpt,
        )
        await tqdm.gather(
            *[_process_task(ctx, t, done, stats) for t in pending],
            desc="Downloading",
            total=len(pending),
        )

    save_checkpoint(done, ckpt)
    log.info(
        "Done. PDF: %d | Text: %d | No content/permanent: %d | Network error (retryable): %d",
        stats["ok_pdf"],
        stats["ok_text"],
        stats["permanent"],
        stats["transient"],
    )


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
        concurrency: Parallel downloads — keep <= 3 in Colab to avoid rate-limiting.
        delay:       Seconds between requests.
        collections: Which collections to scrape (default: all four).
        checkpoint:  Path to the checkpoint JSON file. Defaults to CHECKPOINT_FILE.
    """
    configure_logging(LOG_FILE)
    output_dir = Path(output).resolve()  # noqa: ASYNC240
    output_dir.mkdir(exist_ok=True, parents=True)
    ckpt = Path(checkpoint) if checkpoint else None
    log.info("Output: %s | Concurrency: %d | Delay: %.1fs", output_dir, concurrency, delay)
    log.info("Collections: %s", ", ".join(collections))
    await run(output_dir, concurrency, delay, collections=collections, checkpoint_file=ckpt)
