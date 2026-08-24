---
name: scrapper-api-backend
description: Work on the FastAPI web app backend (src/scrapper_api/) that wraps the Rosario scraper CLI — session/subprocess model, auth, API contract, testing.
---

# Scrapper API backend

`src/scrapper_api/` is a FastAPI backend that lets a browser trigger, monitor, and
download Rosario scrapes. It is a **thin wrapper around the existing CLI** — it
never imports or modifies `src/scrapper/`. Read `CLAUDE.md`'s "Web app architecture"
section first for the high-level picture; this file goes deeper on how to actually
work in this package.

## Run it locally

```bash
uv sync                                  # installs the `api` dependency group too (default-groups)
uv run poe api                           # uvicorn --reload on :8000, interactive docs at /docs
uv run pytest tests/api                  # backend test suite
uv run poe check                         # lint + mypy strict — covers scrapper_api since it's under src/
```

Useful env vars (see `scrapper_api/config.py::Settings`, all overridable, or use a
local `.env` file): `DATA_DIR` (default `./data`), `WEBAPP_USERNAME` (default
`admin`), `WEBAPP_PASSWORD_HASH` (default empty — **login always fails until you
set this**), `SESSION_SECRET`, `CORS_ORIGINS` (default `["http://localhost:5173"]`,
matching the frontend's default Vite port).

Generate a bcrypt hash for local testing:

```bash
uv run python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt'], deprecated='auto').hash('your-password'))"
```

## Why a subprocess, not an in-process import

`scrapper.common.logging_setup.configure_logging()` calls `logging.basicConfig(...)`,
which is a **process-global no-op after the first call**. If two scrape sessions ever
called `rosario_pipeline.run()` in the same process, the second session's logging
setup would silently do nothing. That's why every session spawns
`uv run python -m scrapper rosario --output <dir> --csv-dir <dir> --checkpoint <file>
--concurrency <n> --delay <s>` as a real subprocess (`asyncio.create_subprocess_exec`)
and captures its combined stdout+stderr line-by-line — never calls `scrapper` code
directly. **Do not "optimize" this into an in-process call.**

## The session/job model (`sessions/manager.py`, `sessions/store.py`)

- One `asyncio.Queue` + a single background consumer task. **Exactly one scrape
  subprocess runs at a time** — this isn't just simplicity, it's what keeps concurrent
  web sessions from hammering the Rosario servers beyond the `concurrency`/`delay`
  guidance already documented in `CLAUDE.md`. Never parallelize this queue.
- Each session is isolated: `data/sessions/<id>/{csv_input/, output/, checkpoint.json,
  execution.log, result.zip}`. No corpus is shared across sessions *by default* —
  re-downloading previously-fetched documents across sessions is the accepted
  baseline behavior, not a bug. An operator can opt out of that per-session via the
  resume-seed feature below.
- `output/manifest.csv` (written by the scraper subprocess itself) is the single
  source of truth for "which files got scraped" — the backend never duplicates that
  into SQLite. `sessions.db` (SQLite via `aiosqlite`) only holds session *metadata*
  (status, timestamps, counts, error messages).
- On FastAPI startup, any session stuck `running` whose PID is dead gets reconciled
  to `interrupted` (`sessions/store.py`'s reconciliation query + `os.kill(pid, 0)`).
- **Cancelling** (`POST /api/sessions/{id}/cancel`, `SessionManager.cancel`): if the
  session is the one currently occupying the worker, sends SIGTERM
  (`process.terminate()`) and sets a `_cancel_requested` flag that
  `_run_cli_subprocess` checks *after* `process.wait()` returns, to record
  `cancelled` instead of `failed` — don't write the `cancelled` status from
  `cancel()` itself for a running session, that would race with the subprocess
  loop's own write once the process actually exits. If it's merely `queued`
  (waiting behind another session), there's no process yet, so `cancel()` writes
  `cancelled` directly; `_run_session` then skips it (checks `status ==
  queued` before ever spawning) when the worker gets to it. SIGTERM is not
  caught anywhere in `scrapper`, so a cancelled run loses progress back to its
  last periodic checkpoint save (every 50 successful downloads) — that's an
  accepted tradeoff, not a bug to fix by adding signal handling to `scrapper`
  itself unless asked.

## Two ways a session's `csv_input/` gets populated

- **`source=upload`**: a ZIP is extracted and validated against
  `scrapper.rosario.config.CSV_CONFIG`'s 10 canonical filenames, reusing the same
  fuzzy (case/whitespace/hyphen-insensitive) matcher `scrapper/rosario/tasks.py`
  already uses — don't require byte-exact filenames.
- **`source=portal`**: `sessions/portal_fetch.py` fetches the 10 CSVs directly from
  Rosario's open-data portal (hardcoded URLs, documented in that file) via `aiohttp`
  (already a base project dependency — don't add a new HTTP client). If any file
  fails after retries, the session goes straight to `failed` and no subprocess is
  ever spawned.

Both paths converge on the same thing: a populated `csv_input/` dir, after which
everything (subprocess invocation, logging, manifest, zip) is identical.

## Optional resume-seed: skipping documents from a previous corpus

`POST /api/sessions` also accepts optional `resume_manifest` / `resume_checkpoint`
uploads — a `manifest.csv` and/or `checkpoint.json` from a corpus already
downloaded elsewhere (a prior CLI/Colab run, or a previous web session's output).
`sessions/resume_seed.py` parses them and `routers/sessions_router.py` pre-seeds
the new session's `checkpoint.json` with what they identify as already-downloaded,
*before* its subprocess ever starts — `sessions/manager.py` needs no changes at
all, since it already points `--checkpoint` at that same path and the CLI's
`load_checkpoint` just reads whatever is there.

The one non-obvious part: `checkpoint.json`'s keys are **absolute destination file
paths** (`scrapper.rosario.tasks.build_task_list`: `key = str(dest)`,
`dest = output_dir / category_folder / filename`), and every session gets a
fresh, uniquely-named `output_dir`. A raw checkpoint/manifest from a *different*
run's paths will never string-match this session's freshly-computed task keys —
uploading one as-is would silently skip nothing. `resume_seed.py` fixes this by
re-deriving `category`/`filename` from each source (manifest.csv rows have those
as explicit columns; a checkpoint key's `Path(key).parent.name` /
`Path(key).name` give the same pair by construction) and rewriting
`new_key = str(new_output_dir / category / filename)` before writing them into
the new checkpoint. If `scrapper.rosario.tasks`'s dest-path formula (folder +
filename) ever changes, this remapping needs to change with it. `SKIP:`-prefixed
checkpoint entries (permanent failures) are carried forward the same way, so a
resumed session doesn't retry known-dead documents either.

## Auth

Single hardcoded operator account. `POST /api/auth/login` checks the password with
`passlib` (bcrypt) against `WEBAPP_PASSWORD_HASH`, then issues an httpOnly,
`Secure`, `SameSite=None` cookie signed with `itsdangerous.TimestampSigner` (not a
full JWT — one user doesn't need JWKS/rotation machinery). `SameSite=None` is
required because the frontend (Storage static website) and backend (Container
Apps) are different origins in production; this also means **`TestClient` in tests needs
`base_url="https://testserver"`**, or httpx silently drops the `Secure` cookie and
every "authenticated" test call 401s for no obvious reason (this bit the original
implementation — see `tests/api/conftest.py`).

## API contract

The REST contract (routes, request/response shapes, status codes) is the interface
the frontend is built against — treat route paths and Pydantic model field names as
a compatibility surface, not an implementation detail. If you change a response
shape, check `frontend/src/api/types.ts` and update it in the same change.

## Coding conventions (non-negotiable for this package)

- **No `dict[str, Any]` / `dict[str, str]` for structured data.** Every shape that
  crosses a boundary — API bodies, SQLite rows, session metadata, manifest rows,
  config — is a `pydantic.BaseModel`. `sessions/store.py` returns Pydantic models to
  its callers, never raw sqlite3 rows or dicts.
- Avoid code smells (duplicated logic, long parameter lists, God-objects) and avoid
  gratuitous `None`/`Optional`. Prefer an enum (`SessionStatus`) over a nullable
  status string; only reach for `X | None` when absence is a genuine, meaningful
  state (e.g. `finished_at` on a still-running session).
- mypy strict and ruff `extend-select=["ALL"]` (repo's existing ignore list) must
  both pass clean — same bar as `src/scrapper/`.

## Testing pattern

`tests/api/` intentionally does real I/O (temp dirs, real SQLite, a mocked
subprocess) unlike the pure-function tests in `tests/test_downloader_pure.py` — that
divergence is expected, keep it isolated to `tests/api/`. Mock
`asyncio.create_subprocess_exec` to avoid ever actually scraping in the test suite;
mock the HTTP layer in portal-fetch tests too (no real network calls in CI). Do a
manual, non-mocked smoke test against the real Rosario CLI/portal whenever you touch
`sessions/manager.py`, `sessions/portal_fetch.py`, or `sessions/upload.py` — automated
tests can't catch every real-world edge case in the actual scraper/portal.
