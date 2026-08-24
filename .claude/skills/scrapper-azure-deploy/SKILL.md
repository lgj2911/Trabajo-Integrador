---
name: scrapper-azure-deploy
description: Provision, redeploy, and troubleshoot the Azure hosting (Storage static website + Container Apps + Storage) for the Rosario scraper web app, in infra/azure/.
---

# Scrapper Azure deployment

`infra/azure/` holds the Bicep infrastructure-as-code, Dockerfile, and deploy
scripts for hosting the web app (`src/scrapper_api/` backend +
`frontend/` React SPA) on Azure. **The full step-by-step walkthrough lives in
`infra/azure/README.md` — read that first for actual commands.** This file is
the "what to know before touching this" companion: invariants, gotchas, and
where to look when something breaks.

## The one invariant that must never be violated

**The backend Container App must never run more than 1 replica.** The scrape
job queue and all session state live in that single process's memory (see
`scrapper-api-backend` skill / `CLAUDE.md`'s "Web app architecture"). Running 2+
replicas doesn't just waste money — different requests would land on different
instances with different in-memory state, silently corrupting behavior (lost
jobs, sessions that "disappear" depending on which replica answers). This is
enforced as a hard-coded Bicep `var` (not a `param`) in
`modules/container-app.bicep` specifically so it can't be overridden via a
parameters file. **Do not change this without first moving session/queue state
out of the process** (e.g. into the shared SQLite DB, or an external store) —
that's a real architecture change, not a config tweak.

## Resources (see `infra/azure/README.md` for the full table + cost estimate)

Storage Account serving the frontend via Blob static-website hosting (not
Azure Static Web Apps — its Free tier only exists in 5 regions, and some
subscription types, e.g. Azure for Students, restrict deployments to a region
allowlist that may not include any of them; a plain Storage account works
anywhere) · Container Apps Environment + App (Consumption, max 1 replica,
backend) · Container Registry (Basic) · a *second* Storage Account +
**Azure Files** share for `/data` (not Blob here — needed for POSIX-ish
semantics a live SQLite file + append-mode logs require; Blob/blobfuse's
weaker locking/consistency is risky for that) · Log Analytics workspace
(required by the Container Apps environment).

Target cost: **~$5–10/month**, meant to run for many months against a ~$100
one-time credit. **Check actual spend in Azure Cost Management after every
first deploy** — the estimate in the README is a sanity check, not a bill.

## Secrets

`WEBAPP_PASSWORD_HASH` and `SESSION_SECRET` are set **only** via
`scripts/set-secrets.sh`, never via a `.bicepparam` file (those are checked
into git — never put real secret values there; they default to empty strings
on purpose). Routine redeploys (`scripts/deploy.sh`) never touch secrets —
that separation is deliberate so a normal code-change redeploy can't
accidentally rotate or wipe credentials.

## Deploying

- **First-time provisioning, redeploying after a code change, rotating
  secrets**: all covered step-by-step in `infra/azure/README.md` — don't
  duplicate those exact commands here, they will drift out of sync.
- **Backend-only redeploy**: `./scripts/deploy.sh <resource-group> <env>`
  (rebuilds the image locally with Docker for `linux/amd64`, pushes it,
  updates the Container App; does not touch secrets or the frontend). Builds
  locally rather than via `az acr build`/ACR Tasks because some subscription
  types (e.g. Azure for Students) get every ACR Tasks request rejected with
  `TasksOperationsNotAllowed`, unrelated to registry settings or region —
  local `docker push` uses a separate capability that restriction doesn't
  touch. Requires Docker installed and running locally.
- **Frontend-only redeploy**: rebuild (`npm run build` with
  `VITE_API_BASE_URL` pointed at the Container App's FQDN) and
  `az storage blob upload-batch -s ./dist -d '$web' --overwrite` against the
  static-website Storage Account (see the README's step 5).
- **Infra changes** (editing a `.bicep` file): re-run the `az deployment group
  create` command — it's idempotent.

## Docker image

`infra/azure/Dockerfile` is a multi-stage build: `uv sync --frozen --no-dev
--group api` in a builder stage (following uv's documented Docker
layer-caching pattern — lockfile+pyproject copied and synced before
application source, so editing app code doesn't invalidate the dependency
layer), then a slim runtime stage with the weasyprint system-library stack
(Pango/Cairo/GDK-Pixbuf + fonts) installed via apt — required because the
backend's subprocess invokes the real `scrapper` package, which uses
weasyprint for `html_to_pdf` tasks. This has been built and run end-to-end
against the real `src/scrapper_api` package (uvicorn boots, `/docs` responds,
weasyprint imports cleanly) — if it ever fails at PDF-render time with a
missing shared library, re-check that apt package list against whatever
weasyprint version is actually pinned in `uv.lock`.

The repo root's `.dockerignore` matters more than it looks: this repo also
holds multi-GB local scrape output at the root (`downloads/`,
`downloads_santa_fe/`) that must never end up in a build context. It's an
allow-list (`*` then `!`-reinclude only `pyproject.toml`, `uv.lock`,
`src/scrapper`, `src/scrapper_api`) rather than a deny-list, specifically so
it doesn't need updating every time something new and large shows up at the
repo root.

## CI (`.github/workflows/ci.yml`)

Validation only (backend `poe check` + `pytest tests`, frontend `lint`/`test`/
`build`) — **no deployment step runs in CI**. Deployment is always the manual/
scripted path above, run by a human with Azure credentials. Don't wire up
auto-deploy-on-merge without discussing it first — this is a low-traffic,
budget-constrained deployment where an unreviewed auto-deploy is a real risk
(cost, or shipping a broken image to the one production replica).

## Bicep validation

If the `bicep` CLI is available (`az bicep install`, or download the
standalone binary), run `bicep build`/`bicep lint` against `main.bicep` and
each module before trusting an edit — `@description(...)` annotations must use
single quotes, not double, which is an easy mistake to make and a real error
Bicep caught during this feature's initial build.
