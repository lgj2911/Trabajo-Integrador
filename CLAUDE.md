# CLAUDE.md — Scrapper

This repository covers only the ingestion (Scrapper) phase of Classiflow, a document
classification project for Municipalidad de Rosario (Argentina). The scraper downloads
municipal documents (PDFs, and Plone HTML pages converted to PDF) from the Rosario and
Santa Fe municipal portals into a local corpus for downstream classification, which is
developed in a separate repository. This repo does not contain any classification,
agent, or web UI code — only the downloader.

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
├── .claude/                        Claude Code project settings
├── documents/                      Reference documents and architecture diagrams
├── notebooks/                      Jupyter notebooks
│   └── colab_downloader.ipynb      Bulk download via Google Colab
├── src/
│   └── scrapper/                   Modular downloader package + CSV metadata
│       ├── __main__.py             `python -m scrapper` entry point
│       ├── cli.py                  Unified CLI (choose municipality: rosario | santafe)
│       ├── common/                 Shared: config, logging, checkpoint, urls, download engine
│       ├── rosario/                Rosario scraper: config, extract, resolve, tasks, htmlpdf, pipeline
│       ├── santafe/                Santa Fe scraper: config, extract, sitemap, tasks, pipeline
│       ├── downloader.py           Back-compat facade -> scrapper.rosario
│       ├── downloader_santa_fe.py  Back-compat facade -> scrapper.santafe
│       └── *.csv                   One CSV per document category (10 types)
├── tests/                          Unit tests for scrapper pure functions
├── pyproject.toml                  Dependencies and tool configuration (managed by uv)
├── uv.lock                         Locked dependency graph
├── .pre-commit-config.yaml         Pre-commit hooks (ruff, mypy, gitleaks, uv-lock)
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

Individual tools (when you need to run one step in isolation):

```bash
uv run poe lint        # lint + format check only
uv run poe typecheck   # mypy only
uv run poe test        # pytest tests/ only
uv run poe fmt         # auto-format (ruff format .)
uv run poe precommit   # full pre-commit run on all files
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

## Conventions

- **Python**: standard library + aiohttp / aiofiles / tqdm / beautifulsoup4 / weasyprint.
- Package source lives in `src/scrapper/`. Tests live in `tests/`.
- All comments, docstrings, and commit messages are in English.
- Line length: 100. Quote style: double. (Configured in `[tool.ruff]`.)
- Type annotations required on all functions in `src/` (mypy strict).

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
