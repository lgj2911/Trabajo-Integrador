# Scrapper Console — Frontend

React + TypeScript + Vite single-page app for triggering, monitoring, and browsing the
output of Rosario municipal document scrape sessions. Talks to the FastAPI backend at
`src/scrapper_api/` (see the repository root `CLAUDE.md`) via the REST API described in
`src/api/types.ts` and `src/api/client.ts`.

## Setup

```bash
npm install
cp .env.example .env   # set VITE_API_BASE_URL if not http://localhost:8000
npm run dev
```

## Scripts

| Command | What it does |
|---------|---------------|
| `npm run dev` | Start the Vite dev server |
| `npm run build` | Type-check (`tsc -b`) and build the production `dist/` bundle |
| `npm run preview` | Preview the production build locally |
| `npm run lint` | ESLint (flat config) over the whole project |
| `npm test` | Run the Vitest test suite once |

## Structure

- `src/api/` — typed REST client (`client.ts`) and API contract types (`types.ts`).
- `src/auth/` — auth context (`GET /api/auth/me` on load) and the `RequireAuth` route guard.
- `src/pages/` — one component per route: login, upload/trigger, executions list,
  execution detail (with live log viewer), files browser.
- `src/components/` — shared UI: status badge, log viewer, file table, upload dropzone,
  app layout/nav.
- `tests/` — Vitest + React Testing Library specs.

Every authenticated request is sent with `credentials: "include"` so the backend's
httpOnly session cookie is attached; any `401` response flips auth state and the
`RequireAuth` guard redirects to `/login`.
