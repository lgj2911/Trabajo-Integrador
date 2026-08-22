# CLAUDE.md — Scrapper

This repository covers only the ingestion (Scrapper) phase of Classiflow, a document
classification project for Municipalidad de Rosario (Argentina). The scraper downloads
municipal documents (PDFs, and Plone HTML pages converted to PDF) from the Rosario and
Santa Fe municipal portals into a local corpus for downstream classification, which is
developed in a separate repository. This repo does not contain any classification or
agent code — classification itself is out of scope and lives in a separate repository.

It does, however, include a small internal **web app** (`src/scrapper_api/` +
`frontend/`) that lets an operator trigger, monitor, and download Rosario scrapes
through a browser instead of the CLI. It is a thin wrapper around the CLI/pipeline
below — it never modifies `src/scrapper/` — and covers **Rosario only** (Santa Fe
stays CLI/Colab-only). See "Web app architecture" further down.

## Architecture

```
Sources (inputs)
  ├── Rosario: municipal CSV dataset (idNormativa, boletines, Plone HTML pages)
  └── Santa Fe: transparency portal (sitemap + normativa pages)
          │
          ▼
  ┌─────────────────────────────────────────────┐
  │                    CLI                       │
  │        `python -m scrapper <municipality>`   │
  │                                               │
  │  Link resolution ──► Download ──► Checkpoint │
  │  (direct_pdf · normativa · boletin_html ·    │
  │   html_to_pdf · scrape_page)                 │
  └─────────────────────────────────────────────┘
          │
          ▼
  Downloaded documents (Phase 1 output — PDFs per category)
```

## Project structure

```
/
├── .claude/                        Claude Code project settings + skills (see below)
├── .github/workflows/ci.yml        CI: backend lint/typecheck/test + frontend lint/test/build
├── documents/                      Reference documents and architecture diagrams
├── notebooks/                      Jupyter notebooks
│   └── colab_downloader.ipynb      Bulk download via Google Colab (optional/legacy path)
├── src/
│   ├── scrapper/                   Modular downloader package + CSV metadata
│   │   ├── __main__.py             `python -m scrapper` entry point
│   │   ├── cli.py                  Unified CLI (choose municipality: rosario | santafe)
│   │   ├── common/                 Shared: config, logging, checkpoint, urls, download engine
│   │   ├── rosario/                Rosario scraper: config, extract, resolve, tasks, htmlpdf, pipeline
│   │   ├── santafe/                Santa Fe scraper: config, extract, sitemap, tasks, pipeline
│   │   ├── downloader.py           Back-compat facade -> scrapper.rosario
│   │   ├── downloader_santa_fe.py  Back-compat facade -> scrapper.santafe
│   │   └── *.csv                   One CSV per document category (10 types)
│   └── scrapper_api/                Web app backend (FastAPI) — see "Web app architecture"
│       ├── app.py, config.py, auth.py, db.py, models.py, dependencies.py
│       ├── sessions/                store, manager (subprocess queue), upload, portal_fetch, manifest_reader
│       └── routers/                 auth_router, sessions_router, files_router
├── frontend/                        Web app frontend (React + Vite + TypeScript SPA)
├── infra/azure/                     Azure infra-as-code: Bicep modules, Dockerfile, deploy scripts
├── tests/
│   ├── test_downloader_pure.py      Unit tests for scrapper pure functions
│   ├── test_downloader_santa_fe_pure.py
│   └── api/                         Backend API tests (auth, sessions, upload, portal-fetch, ...)
├── pyproject.toml                  Dependencies and tool configuration (managed by uv)
├── uv.lock                         Locked dependency graph
├── .pre-commit-config.yaml         Pre-commit hooks (ruff, mypy, gitleaks, uv-lock, frontend-lint)
└── DEPLOY.md                       Deployment options and scale estimates
```

## Environment setup

```bash
uv sync --dev          # install all deps (runtime + dev group) into .venv
```

The `.venv/` directory is gitignored. Always use `uv sync` — do not use `pip install`.

## Running the downloader (ingestion Phase 1)

The scraper is a package with a unified CLI. Choose the municipality with the
first argument:

```bash
# Municipalidad de Rosario (primary ingestion target)
uv run python -m scrapper rosario --output ./downloads --concurrency 5 --delay 0.5

# Municipalidad de Santa Fe (test corpus for classification validation)
uv run python -m scrapper santafe --output ./downloads_santa_fe --concurrency 5 --delay 0.5
```

Shared arguments:
- `--output` — destination folder
- `--concurrency` — parallel downloads, keep ≤ 5 to avoid rate-limiting (default: 5)
- `--delay` — seconds between requests (default: 0.5)
- `--checkpoint` — path to the checkpoint JSON file

Rosario also accepts `--csv-dir`; Santa Fe accepts `--collections`.

A checkpoint file tracks progress (`checkpoint.json` for Rosario,
`checkpoint_santa_fe.json` for Santa Fe); re-running skips already-downloaded files.

Each run also appends to `manifest.csv` inside `--output` — a human-readable ledger
(timestamp, source, category, filename, source URL, destination path) of every
document saved, one row per download.

## Web app architecture

```
Browser (React SPA, frontend/)
  │  cookie auth, credentials:"include"
  ▼
FastAPI backend (src/scrapper_api/)
  │
  │  POST /api/sessions  {source: upload|portal}
  ▼
┌───────────────────────────────────────────────────────────────────┐
│ SessionManager — one asyncio.Queue + a SINGLE background consumer  │
│ (exactly one scrape subprocess at a time, by design — see below)   │
│                                                                     │
│  [portal source only] fetch 10 CSVs from Rosario open-data portal  │
│         │                                                          │
│         ▼                                                          │
│  subprocess: uv run python -m scrapper rosario                     │
│              --output <dir> --csv-dir <dir> --checkpoint <file>    │
│              --concurrency <n> --delay <s>                         │
│         │  (src/scrapper is NEVER imported/modified — it's         │
│         │   invoked exactly like the CLI, as a black box)          │
│         ▼                                                          │
│  stdout+stderr captured line-by-line → execution.log + live SSE    │
└───────────────────────────────────────────────────────────────────┘
         │
         ▼
data/sessions/<session_id>/{csv_input/, output/, checkpoint.json,
                             execution.log, result.zip}
  output/manifest.csv is the source of truth for "scrapped files" —
  no data is duplicated into SQLite; sessions.db only holds session
  metadata (status, timestamps, counts).
```

Key invariants (do not casually change these — see
`.claude/skills/scrapper-api-backend/SKILL.md` for the full rationale):

- **`src/scrapper/` is never imported or modified by the backend.** It's
  invoked as a subprocess, exactly like a human running the CLI. This is
  required, not just a style choice: `configure_logging()` calls
  `logging.basicConfig(...)`, which is a process-global no-op after the first
  call — multiple sessions can never safely share one Python process.
- **Exactly one scrape subprocess runs at a time**, queued in-process. This
  both respects the "concurrency ≤ 5" rate-limit guidance above and avoids
  needing any cross-process coordination.
- **The backend must never run with more than 1 replica in production** — the
  job queue and session state live in that one process's memory, not in a
  shared/external store. `infra/azure/modules/container-app.bicep` hard-codes
  `maxReplicas` to enforce this.
- Sessions are isolated (own `csv_input/`, `output/`, `checkpoint.json`) —
  no corpus is shared across sessions, which is what makes "zip and download
  this session's output" trivial and correct.
- All structured Python data in `scrapper_api` is a `pydantic.BaseModel`, never
  a bare `dict[str, Any]`/`dict[str, str]` — see the backend skill file.

## Code revision

**Run after every modification:**

```bash
uv run poe check
```

This is the single verification gate. It runs in order:

| Step | Command | What it checks |
|------|---------|---------------|
| `lint` | `ruff check . && ruff format --check .` | Style and lint rules |
| `typecheck` | `mypy src && nbqa mypy notebooks` | Type correctness |
| `nbtest` | `pytest --nbmake notebooks` | Notebooks execute without error |

`poe check` covers `src/scrapper_api/` too (same mypy-strict/ruff config, since
it lives under `src/`). It does **not** run `pytest`; run that separately.

Individual tools (when you need to run one step in isolation):

```bash
uv run poe lint        # lint + format check only
uv run poe typecheck   # mypy only
uv run poe test        # pytest tests/ only (includes tests/api/)
uv run poe fmt         # auto-format (ruff format .)
uv run poe api         # run the web app backend locally (uvicorn --reload, port 8000)
uv run poe precommit   # full pre-commit run on all files
```

For the frontend (`frontend/`, not covered by the Python tooling above):

```bash
cd frontend
npm install
npm run lint     # eslint
npm test         # vitest
npm run build    # production build -> frontend/dist
npm run dev      # local dev server, port 5173
```

Hooks enforced on every commit (see `.pre-commit-config.yaml`):

| Hook | What it checks |
|------|---------------|
| `trailing-whitespace` | Trailing spaces |
| `end-of-file-fixer` | Files end with a newline |
| `check-yaml` | Valid YAML syntax |
| `debug-statements` | No `breakpoint()` / `pdb` left in code |
| `uv-lock` | `uv.lock` is in sync with `pyproject.toml` |
| `gitleaks` | No secrets committed |
| `ruff-format` | Code formatted per ruff config |
| `ruff-check` | Lint rules (exits non-zero if fixes were applied) |
| `mypy` | Type correctness of `src/` |
| `nbqa-mypy` | Type correctness of notebooks |
| `frontend-lint` | `cd frontend && npm run lint`, local-only, only runs when `frontend/**/*.{ts,tsx}` changed |

## Conventions

- **Python**: standard library + aiohttp / aiofiles / tqdm / beautifulsoup4 / weasyprint
  (`scrapper`), plus fastapi / uvicorn / aiosqlite / itsdangerous / passlib / pydantic-settings
  (`scrapper_api`).
- Package source lives in `src/scrapper/` and `src/scrapper_api/`. Tests live in `tests/`
  (`tests/api/` for the backend).
- All comments, docstrings, and commit messages are in English.
- Line length: 100. Quote style: double. (Configured in `[tool.ruff]`.)
- Type annotations required on all functions in `src/` (mypy strict) — this applies to
  `scrapper_api` too.
- **In `scrapper_api` (and any new Python for this project generally): use `pydantic.BaseModel`
  for structured data, never `dict[str, Any]`/`dict[str, str]`; avoid code smells and
  gratuitous `None`/`Optional`.** See `.claude/skills/scrapper-api-backend/SKILL.md` for
  the full rule and rationale.
- Frontend (`frontend/`): React + Vite + TypeScript, ESLint + Vitest. See
  `.claude/skills/scrapper-webapp-frontend/SKILL.md`.

## Git workflow

**Commits, pushes, and pull requests are always initiated by the human.**
Claude prepares and verifies changes but never commits, pushes, or opens PRs autonomously.

## Downloader link resolution strategies

| Type | How it works |
|------|-------------|
| `direct_pdf` | URL already points to the PDF |
| `normativa` | Extracts `idNormativa` and builds a direct download URL |
| `boletin_html` | Scrapes bulletin index page to find internal PDF IDs |
| `html_to_pdf` | Downloads a Plone HTML page and converts it via weasyprint |
| `scrape_page` | Generic scraping for compendium pages |

## Downloaded documents (Phase 1 output)

Available on Google Drive:
https://drive.google.com/drive/folders/1_IPfa4m1mmz6wFPOLtEf3T4xYknJap7B?usp=drive_link

## Web app hosting

See `DEPLOY.md` for the Azure hosting overview (cost estimate, resource list)
and `infra/azure/README.md` for the full step-by-step deployment walkthrough.
