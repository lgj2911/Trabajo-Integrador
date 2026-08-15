# Scrapper

The ingestion (Phase 1) component of Classiflow, a document classification project for
Municipalidad de Rosario (Argentina). This repository covers only the downloader: it
fetches municipal documents from the Rosario and Santa Fe portals into a local corpus.
Classification, confidence scoring, and the web/chat interface are developed in a
separate repository and are out of scope here.

## Repository Structure

```
/
├── .claude/                        Claude Code project settings
├── documents/                      Reference documents and architecture diagrams
├── notebooks/                      Jupyter notebooks
│   └── colab_downloader.ipynb      Bulk download via Google Colab
├── src/
│   └── scrapper/                   Phase 1 — modular downloader package + CSV metadata
│       ├── __main__.py             `python -m scrapper` entry point
│       ├── cli.py                  Unified CLI (choose municipality: rosario | santafe)
│       ├── common/                 Shared: config, logging, checkpoint, urls, download engine
│       ├── rosario/                Rosario scraper (config, extract, resolve, tasks, htmlpdf, pipeline)
│       ├── santafe/                Santa Fe scraper (config, extract, sitemap, tasks, pipeline)
│       └── *.csv                   One CSV per document category (10 types)
├── tests/                          Unit tests for scrapper pure functions
├── pyproject.toml                  Dependencies and tool configuration (managed by uv)
└── uv.lock                         Locked dependency graph
```

## Document Categories

The dataset covers 10 categories of municipal documents from Rosario's open-data portal:

| Category | Description |
|----------|-------------|
| `boletines` | Municipal bulletins |
| `compendios_de_boletines` | Bulletin compendiums |
| `convenios` | Agreements |
| `declaraciones_concejo_municipal` | Municipal council declarations |
| `decreto_ordenanzas` | Decree-ordinances |
| `decretos` | Decrees |
| `decretos_concejo_municipal` | Municipal council decrees |
| `ordenanzas` | Ordinances |
| `resoluciones` | Resolutions |
| `resoluciones_concejo_municipal` | Municipal council resolutions |

The ingested documents (Phase 1 output) are available on [Google Drive](https://drive.google.com/drive/folders/1_IPfa4m1mmz6wFPOLtEf3T4xYknJap7B?usp=drive_link).

## Setup

```bash
uv sync --dev
```

Always use `uv sync` — do not use `pip install`.

## Running the Downloader (Phase 1)

The scraper is a package with a unified CLI. Choose the municipality with the
first argument:

```bash
# Municipalidad de Rosario (primary ingestion target)
uv run python -m scrapper rosario --output ./downloads --concurrency 5 --delay 0.5

# Municipalidad de Santa Fe (test corpus for classification validation)
uv run python -m scrapper santafe --output ./downloads_santa_fe --concurrency 5 --delay 0.5
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--output` | `./downloads` | Destination folder for the documents |
| `--concurrency` | `5` | Parallel downloads — keep ≤ 5 to avoid rate-limiting |
| `--delay` | `0.5` | Seconds between requests |
| `--checkpoint` | per municipality | Path to the checkpoint JSON file |

Rosario also accepts `--csv-dir`; Santa Fe accepts `--collections`. A checkpoint
file tracks progress (`checkpoint.json` for Rosario, `checkpoint_santa_fe.json`
for Santa Fe); re-running skips already-downloaded files.

Alternatively, open `notebooks/colab_downloader.ipynb` in Google Colab to run the downloader using cloud resources without any local setup.

## Development

```bash
uv run poe check   # lint + type check + notebook tests (run after every change)
uv run poe fmt     # auto-format
uv run poe test    # unit tests only
```
