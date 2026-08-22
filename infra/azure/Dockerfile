# syntax=docker/dockerfile:1
#
# Multi-stage build for the scrapper FastAPI backend (scrapper_api.app:app).
#
# Build from the repo root, e.g.:
#   docker build -f infra/azure/Dockerfile -t scrapper-api:local .
#
# NOTE ON THE "api" DEPENDENCY GROUP: the backend's FastAPI runtime dependencies
# (fastapi, uvicorn, aiosqlite, itsdangerous, passlib, pydantic-settings, etc.)
# live in the uv dependency-group named "api" in the repo-root pyproject.toml.
# This image has been built and run end-to-end against the finalized
# src/scrapper_api package (uvicorn boots, /docs and /openapi.json respond,
# weasyprint imports successfully with the system libs installed below).

# ---- Builder stage -------------------------------------------------------
# Installs uv (pinned to the same version the dev tooling uses, see
# pyproject.toml's dev group: "uv==0.8.9") and syncs dependencies into a
# virtualenv, following uv's documented Docker layer-caching pattern:
# https://docs.astral.sh/uv/guides/integration/docker/
#   1. copy only the lockfile + pyproject.toml, sync deps (no project code yet)
#   2. copy the actual source packages, sync again to install the project itself
# This way, editing application source doesn't invalidate the (slow) dependency
# resolution/download layer.
FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.8.9 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --group api --no-install-project

# Only the two packages this image actually ships. Deliberately not COPYing the
# whole repo (tests/, frontend/, notebooks/, downloads/, ...) to keep this layer
# small and avoid unrelated files busting the cache.
COPY src/scrapper ./src/scrapper
COPY src/scrapper_api ./src/scrapper_api

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --group api

# ---- Runtime stage ---------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# System libraries required by weasyprint at runtime (the Pango/Cairo/GDK-Pixbuf
# text-shaping and rendering stack used to convert Plone HTML pages to PDF), plus
# a font package so rendered PDFs have glyphs to draw. This list matches
# weasyprint's documented Debian/Ubuntu dependency list as of the 61.x-62.x series
# (see https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#debian-ubuntu).
# Re-verify against the weasyprint version actually pinned in uv.lock if the image
# ever fails at PDF-render time with a missing shared library error.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
        shared-mime-info \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

# Mounted as an Azure Files-backed volume by the Container App in production (see
# infra/azure/modules/container-app.bicep); declared here too so a plain
# `docker run` gets a sane default mount point.
VOLUME ["/data"]

EXPOSE 8000

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data /app
USER appuser

CMD ["uvicorn", "scrapper_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
