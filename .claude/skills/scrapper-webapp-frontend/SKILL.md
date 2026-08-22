---
name: scrapper-webapp-frontend
description: Work on the React/Vite frontend (frontend/) for the Rosario scraper web app — pages, API client, auth, SSE logs, testing.
---

# Scrapper web app frontend

`frontend/` is a React + Vite + TypeScript single-page app that's the browser UI for
`src/scrapper_api/` (see that package's own skill, `scrapper-api-backend`, and
`CLAUDE.md`'s "Web app architecture" section for the backend side). It is a fully
separate npm project — not covered by the repo's Python tooling (`poe check`,
mypy, ruff) at all.

## Run it locally

```bash
cd frontend
npm install
npm run dev          # dev server on :5173, expects VITE_API_BASE_URL (see .env.example)
npm run lint         # eslint
npm test             # vitest
npm run build        # production build -> frontend/dist (what Static Web Apps serves)
```

By default `VITE_API_BASE_URL=http://localhost:8000`, matching the backend's default
`uv run poe api` port and its default `CORS_ORIGINS=["http://localhost:5173"]` — the
two default configs are meant to work together out of the box for local dev.

## The 4 pages

- **Login** (`pages/LoginPage.tsx`) — the whole app is gated; every API call uses
  `credentials: "include"` (see `api/client.ts`) so the httpOnly auth cookie rides
  along automatically.
- **New scrape / Upload** (`pages/UploadPage.tsx`) — two modes: upload a ZIP of the
  10 Rosario CSVs, or trigger a "fetch from Rosario Open Data" run with no file at
  all. Both `POST /api/sessions` with a different `source` field and redirect to
  the new session's detail page.
- **Executions** (`pages/ExecutionsPage.tsx` + `ExecutionDetailPage.tsx`) — the
  session history + live view. The list page polls (`setInterval`) only while a
  session is `queued`/`running` — it's a list, not a stream, so plain polling is
  the right tool there. The detail page opens a real `EventSource` against
  `/api/sessions/{id}/logs` for the live log tail.
- **Files** (`pages/FilesPage.tsx`) — a filterable table backed by `GET /api/files`
  (aggregated across all sessions' `manifest.csv` files on the backend). The 10
  known categories for the filter dropdown live in `api/types.ts` as
  `FILE_CATEGORIES` — keep this list in sync with `scrapper.rosario.config.CSV_CONFIG`
  if that ever changes.

## SSE and cross-origin cookies

`LogViewer` consumes `EventSource`, which does **not** send cookies cross-origin by
default. In production, frontend (Static Web Apps) and backend (Container Apps) are
different origins, so the `EventSource` must be constructed with
`{ withCredentials: true }` or the log stream will silently 401/fail auth. This is
easy to miss locally since same-origin-adjacent `localhost` setups can mask it —
always re-check this if the log viewer stops working after a deploy.

## API contract

`api/types.ts` mirrors `scrapper_api`'s Pydantic response models field-for-field.
Treat this as a compatibility surface with the backend, not a local convenience type
— if you add/rename a field here, the backend's `src/scrapper_api/models.py` needs
the matching change (and vice versa), or requests/responses will silently
mismatch at runtime (TypeScript won't catch a backend-only rename).

## Testing

Vitest + React Testing Library, with `tests/setup.ts` doing explicit
`afterEach(cleanup)` (globals are off, so this doesn't happen automatically). Mock
`apiClient` and `EventSource` rather than standing up a real backend for unit tests
— keep it fast and hermetic. Do a manual pass against a real, locally-running
`scrapper_api` backend (`uv run poe api`) whenever you touch auth, the upload flow,
or the log viewer — these are exactly the paths that can't be fully verified with
mocks alone (real cookie behavior, real SSE, real multipart upload).

## Conventions

- Keep dependencies minimal — a router (`react-router-dom`) and plain CSS is enough
  for this internal tool; don't pull in a heavy component library.
- ESLint clean, `npm run build` producing a working `dist/` with no type errors —
  same non-negotiable bar as the Python side's `poe check`.
