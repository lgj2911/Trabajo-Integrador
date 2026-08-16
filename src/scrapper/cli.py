"""Unified CLI for the municipal document scrapers.

Choose the municipality with the first positional argument:

    python -m scrapper rosario  [--output ...] [--concurrency N] [--delay S]
                                [--csv-dir ...] [--checkpoint ...]
    python -m scrapper santafe  [--output ...] [--concurrency N] [--delay S]
                                [--collections ...] [--checkpoint ...]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from scrapper.common.logging_setup import configure_logging
from scrapper.rosario import config as rosario_config
from scrapper.rosario import pipeline as rosario_pipeline
from scrapper.santafe import config as santafe_config
from scrapper.santafe import pipeline as santafe_pipeline

log = logging.getLogger(__name__)


def _add_common_args(parser: argparse.ArgumentParser, default_output: str) -> None:
    """Register the CLI arguments shared by every municipality."""
    parser.add_argument("--output", default=default_output)
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
        "--checkpoint",
        default=None,
        help="Path to the checkpoint JSON file (default: next to the scrapper package)",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with one subcommand per municipality.

    Returns:
        The configured top-level parser.
    """
    parser = argparse.ArgumentParser(
        prog="scrapper",
        description="Bulk downloader for municipal documents (Rosario / Santa Fe)",
    )
    sub = parser.add_subparsers(dest="municipality", required=True, metavar="{rosario,santafe}")

    p_rosario = sub.add_parser("rosario", help="Municipalidad de Rosario (open-data CSVs)")
    _add_common_args(p_rosario, "./downloads")
    p_rosario.add_argument(
        "--csv-dir",
        default=None,
        help="Path to the folder containing CSV files (overrides SCRAPPER_DIR env var)",
    )

    p_santafe = sub.add_parser("santafe", help="Municipalidad de Santa Fe (transparency portal)")
    _add_common_args(p_santafe, "./downloads_santa_fe")
    p_santafe.add_argument(
        "--collections",
        nargs="+",
        default=list(santafe_config.ALL_COLLECTIONS),
        choices=list(santafe_config.ALL_COLLECTIONS),
        metavar="COLLECTION",
        help=f"Collections to scrape (default: all). Choices: "
        f"{', '.join(santafe_config.ALL_COLLECTIONS)}",
    )

    return parser


def _run_rosario(args: argparse.Namespace) -> None:
    """Dispatch a parsed rosario command to the Rosario pipeline."""
    configure_logging(rosario_config.LOG_FILE)
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_dir = Path(args.csv_dir) if args.csv_dir else None
    checkpoint_file = Path(args.checkpoint) if args.checkpoint else None

    log.info("csv_dir: %s", csv_dir or rosario_config.SCRAPPER_DIR)
    log.info(
        "Output: %s | Concurrency: %d | Delay: %.1fs", output_dir, args.concurrency, args.delay
    )
    asyncio.run(
        rosario_pipeline.run(
            output_dir,
            args.concurrency,
            args.delay,
            csv_dir=csv_dir,
            checkpoint_file=checkpoint_file,
        )
    )


def _run_santafe(args: argparse.Namespace) -> None:
    """Dispatch a parsed santafe command to the Santa Fe pipeline."""
    configure_logging(santafe_config.LOG_FILE)
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_file = Path(args.checkpoint) if args.checkpoint else None
    collections = tuple(args.collections)

    log.info(
        "Output: %s | Concurrency: %d | Delay: %.1fs", output_dir, args.concurrency, args.delay
    )
    log.info("Collections: %s", ", ".join(collections))
    asyncio.run(
        santafe_pipeline.run(
            output_dir,
            args.concurrency,
            args.delay,
            collections=collections,
            checkpoint_file=checkpoint_file,
        )
    )


def main(argv: list[str] | None = None) -> None:
    """Parse *argv* and run the selected municipality's scraper."""
    args = build_parser().parse_args(argv)
    if args.municipality == "rosario":
        _run_rosario(args)
    else:
        _run_santafe(args)


if __name__ == "__main__":
    main()
