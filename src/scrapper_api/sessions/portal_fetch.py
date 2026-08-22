"""Fetch Rosario's 10 open-data CSVs directly from the transparency portal.

This is the alternative to uploading a zip: instead of the user supplying the
CSVs, we download them ourselves from Rosario's open-data portal
(https://datosabiertos.rosario.gob.ar/) into a session's ``csv_input/`` directory,
under their canonical filenames (matching ``scrapper.rosario.config.CSV_CONFIG``).

The URLs below were captured manually from that portal's "Normativa municipal"
dataset resource listing.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from pathlib import Path

log = logging.getLogger(__name__)

_PORTAL_BASE = "https://datosabiertos.rosario.gob.ar/sites/default/files/resources/"

#: canonical filename (matches scrapper.rosario.config.CSV_CONFIG) -> portal resource filename
PORTAL_CSV_FILES: dict[str, str] = {
    "boletines.csv": "boletines_0.csv",
    "compendios_de_boletines.csv": "compendios_0.csv",
    "convenios.csv": "normativas_conv.csv",
    "declaraciones_concejo_municipal.csv": "normativas_decla_cm.csv",
    "decreto_ordenanzas.csv": "normativas_dec_ord_0.csv",
    "decretos.csv": "normativas_dec_0.csv",
    "decretos_concejo_municipal.csv": "normativas_dec_cm_0.csv",
    "ordenanzas.csv": "normativas_ord_0.csv",
    "resoluciones.csv": "normativas_res_0.csv",
    "resoluciones_concejo_municipal.csv": "normativas_res_cm.csv",
}

MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 1.0
_HTTP_OK = 200

LogSink = Callable[[str], Awaitable[None]]


class PortalFetchError(Exception):
    """Raised when a CSV could not be fetched after all retry attempts."""


async def _attempt_download(
    session: aiohttp.ClientSession, url: str, destination_file: Path
) -> tuple[bool, str]:
    """Perform a single GET attempt, writing the body to *destination_file* on success.

    Returns:
        ``(True, "")`` on success, or ``(False, <error description>)`` on failure.
    """
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != _HTTP_OK:
                return False, f"HTTP {resp.status}"
            body = await resp.read()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        return False, str(exc)

    await asyncio.to_thread(destination_file.write_bytes, body)
    return True, ""


async def _fetch_one(
    session: aiohttp.ClientSession,
    canonical_name: str,
    resource_name: str,
    destination: Path,
    on_log: LogSink,
) -> None:
    """Download one CSV into *destination*, retrying up to MAX_ATTEMPTS times.

    Raises:
        PortalFetchError: if every attempt fails.
    """
    url = _PORTAL_BASE + resource_name
    destination_file = destination / canonical_name
    last_error = "unknown error"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        ok, last_error = await _attempt_download(session, url, destination_file)
        if ok:
            await on_log(f"Fetched {canonical_name} from portal: {destination_file.name}")
            return

        await on_log(f"Attempt {attempt}/{MAX_ATTEMPTS} for {canonical_name} failed: {last_error}")
        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(_RETRY_DELAY_SECONDS)

    msg = f"Failed to fetch {canonical_name} from the Rosario open-data portal: {last_error}"
    raise PortalFetchError(msg)


async def fetch_all(destination: Path, on_log: LogSink) -> list[str]:
    """Fetch all 10 canonical CSVs into *destination*, logging progress via *on_log*.

    Stops at (and propagates) the first CSV that fails after all retries -- no
    further CSVs are attempted once one has permanently failed.

    Returns:
        The canonical filenames written, in ``PORTAL_CSV_FILES`` order.
    """
    await asyncio.to_thread(destination.mkdir, parents=True, exist_ok=True)
    written: list[str] = []
    async with aiohttp.ClientSession() as session:
        for canonical_name, resource_name in PORTAL_CSV_FILES.items():
            await _fetch_one(session, canonical_name, resource_name, destination, on_log)
            written.append(canonical_name)
    return written
