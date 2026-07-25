"""Orchestrator for the Municipalidad de Rosario scraper."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import aiohttp
from tqdm.asyncio import tqdm

from scrapper.common.checkpoint import (
    SKIP_PREFIX,
    is_pending,
    load_checkpoint,
    save_checkpoint,
)
from scrapper.common.downloader import DownloadCtx, download_pdf
from scrapper.common.logging_setup import configure_logging
from scrapper.rosario.config import CHECKPOINT_FILE, LOG_FILE, SCRAPPER_DIR
from scrapper.rosario.htmlpdf import html_to_pdf_file
from scrapper.rosario.resolve import resolve_pdf_url
from scrapper.rosario.tasks import RosarioTask, build_task_list, expand_boletin_tasks

log = logging.getLogger(__name__)


def _apply_migration(
    tasks: list[RosarioTask], done: set[str], checkpoint_file: Path | None = None
) -> None:
    """Unblock tasks previously marked SKIP that now have a dedicated handler.

    Mutates *done* in place and persists the checkpoint when entries are removed.
    """
    newly_supported = {"boletin_html", "html_to_pdf"}
    keys_to_unblock = {SKIP_PREFIX + t["key"] for t in tasks if t["link_type"] in newly_supported}
    removed = len(done & keys_to_unblock)
    if removed:
        done -= keys_to_unblock
        save_checkpoint(done, checkpoint_file or CHECKPOINT_FILE)
        log.info("Migration: %d SKIP entries unblocked for reprocessing", removed)


async def _expand_boletines(
    session: aiohttp.ClientSession,
    tasks: list[RosarioTask],
    done: set[str],
    delay: float,
    checkpoint_file: Path,
) -> list[RosarioTask]:
    """Phase 1: replace boletin_html container tasks with their individual PDF tasks.

    Returns:
        Updated task list with boletin_html entries replaced by expanded PDF tasks.
    """
    boletin_html_tasks = [
        t for t in tasks if t["link_type"] == "boletin_html" and is_pending(t["key"], done)
    ]
    if not boletin_html_tasks:
        return tasks
    log.info("Expanding %d HTML boletines...", len(boletin_html_tasks))
    expanded = await expand_boletin_tasks(session, boletin_html_tasks, delay)
    log.info("-> %d internal PDFs found in boletines", len(expanded))
    done.update(SKIP_PREFIX + t["key"] for t in boletin_html_tasks)
    save_checkpoint(done, checkpoint_file)
    return [t for t in tasks if t["link_type"] != "boletin_html"] + expanded


async def _filter_pending(tasks: list[RosarioTask], done: set[str]) -> list[RosarioTask]:
    """Phase 2: return tasks that are pending and not already present on disk.

    Returns:
        Subset of *tasks* that still need to be downloaded or converted.
    """
    return [
        t
        for t in tasks
        if is_pending(t["key"], done) and not await asyncio.to_thread(os.path.exists, t["key"])
    ]


def _log_progress(tasks: list[RosarioTask], pending: list[RosarioTask], done: set[str]) -> None:
    """Log a summary of task counts before starting downloads."""
    skipped = sum(1 for t in tasks if (SKIP_PREFIX + t["key"]) in done)
    ok_prev = sum(1 for t in tasks if t["key"] in done)
    log.info(
        "Total: %d | Previously OK: %d | Skipped: %d | Pending: %d",
        len(tasks),
        ok_prev,
        skipped,
        len(pending),
    )


async def _process_task(
    ctx: DownloadCtx,
    task: RosarioTask,
    done: set[str],
    stats: dict[str, int],
) -> None:
    """Download or convert a single task, updating *done* and *stats* in place."""
    async with ctx.semaphore:
        outcome: bool | str | None = None

        if task["link_type"] == "html_to_pdf":
            outcome = await html_to_pdf_file(ctx.session, task["page_url"], task["dest"], ctx.delay)
        else:
            result = await resolve_pdf_url(
                ctx.session, task["page_url"], task["link_type"], ctx.delay
            )
            if result == "PERMANENT":
                outcome = "PERMANENT"
            elif result is not None:
                outcome = await download_pdf(
                    ctx.session, result, task["dest"], ctx.delay, not_found_permanent=False
                )

        if outcome is True:
            stats["ok"] += 1
            done.add(task["key"])
            if stats["ok"] % 50 == 0 and ctx.checkpoint_file is not None:
                save_checkpoint(done, ctx.checkpoint_file)
                log.info("Checkpoint: %d OK so far", stats["ok"])
        elif outcome == "PERMANENT":
            stats["permanent"] += 1
            done.add(SKIP_PREFIX + task["key"])
        else:
            stats["transient"] += 1


async def run(
    output_dir: Path,
    concurrency: int,
    delay: float,
    csv_dir: Path | None = None,
    checkpoint_file: Path | None = None,
) -> None:
    """Run the full Rosario download pipeline."""
    ckpt = checkpoint_file or CHECKPOINT_FILE
    tasks = build_task_list(output_dir, csv_dir=csv_dir)
    done = load_checkpoint(ckpt)
    _apply_migration(tasks, done, ckpt)

    connector = aiohttp.TCPConnector(limit=concurrency, ssl=False)
    stats: dict[str, int] = {"ok": 0, "permanent": 0, "transient": 0}

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = await _expand_boletines(session, tasks, done, delay, ckpt)
        pending = await _filter_pending(tasks, done)
        _log_progress(tasks, pending, done)

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
        "Done. OK: %d | No PDF/permanent: %d | Network error (retryable): %d",
        stats["ok"],
        stats["permanent"],
        stats["transient"],
    )


async def run_colab(
    output: str = "./downloads",
    concurrency: int = 3,
    delay: float = 1.0,
    csv_dir: str | None = None,
    checkpoint: str | None = None,
) -> None:
    """Async entry point for Google Colab notebooks.

    Call with ``await run_colab(...)`` in a notebook cell.

    Args:
        output:      Destination folder for downloaded PDFs.
        concurrency: Parallel downloads — keep <= 3 in Colab to avoid rate-limiting.
        delay:       Seconds between requests.
        csv_dir:     Path to the folder containing the CSV files. Defaults to
                     SCRAPPER_DIR (set via env var or module default).
        checkpoint:  Path to the checkpoint JSON file. Defaults to CHECKPOINT_FILE.
    """
    configure_logging(LOG_FILE)
    output_dir = Path(output).resolve()  # noqa: ASYNC240
    output_dir.mkdir(exist_ok=True, parents=True)
    src = Path(csv_dir) if csv_dir else SCRAPPER_DIR
    ckpt = Path(checkpoint) if checkpoint else None
    log.info("csv_dir: %s | checkpoint: %s", src, ckpt or CHECKPOINT_FILE)
    log.info("Output: %s | Concurrency: %d | Delay: %.1fs", output_dir, concurrency, delay)
    await run(output_dir, concurrency, delay, csv_dir=src, checkpoint_file=ckpt)
