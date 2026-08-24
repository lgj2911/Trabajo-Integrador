# Azure infrastructure — Rosario scraper web app

Infrastructure-as-code for deploying the scraper's web app (FastAPI backend +
React frontend) to Azure. This is a from-zero, step-by-step walkthrough for a
human running `az` CLI commands — nothing here deploys itself, and nothing in
CI deploys either (see `.github/workflows/ci.yml`).

## Architecture / resources provisioned

| Resource | Tier / SKU | Purpose |
|---|---|---|
| Resource Group | — | Container for everything below (created manually, once, per environment) |
| Storage Account (static website / `$web` blob container) | **Standard_LRS** | Hosts the built React frontend (`frontend/dist`) |
| Azure Container Apps (environment + app) | **Consumption**, scale 0-1 | Runs the FastAPI backend container |
| Azure Container Registry | **Basic** | Stores the backend's Docker image |
| Storage Account + Azure Files share | **Standard_LRS** | Persistent `/data` volume (SQLite DB + per-session scrape logs/output) mounted into the Container App |
| Log Analytics workspace | **PerGB2018**, 30-day retention | Required by the Container Apps environment for logs |

**Why a Storage static website and not Azure Static Web Apps:** SWA's Free
tier only exists in 5 regions (`eastus2`, `centralus`, `westus2`,
`westeurope`, `eastasia`). Some subscription types (e.g. Azure for Students)
restrict deployments to a subscription-specific region allowlist that may not
intersect with that list at all — see the Troubleshooting section below. A
plain Storage account works in any region, so this sidesteps the constraint
entirely, and drops the separate SWA CLI dependency.

**Hard requirement — max replicas is 1.** The backend keeps in-process
job-queue state and session-manager state in memory (see `src/scrapper_api`).
Running more than one replica would let different requests land on different
instances with different in-memory state — silently *wrong* behavior (lost
jobs, inconsistent sessions), not just wasted spend. `modules/container-app.bicep`
hard-codes `maxReplicas` as a `var`, not a `param`, specifically so it can't be
overridden from a parameters file. Do not change this without first moving that
state out of the process (e.g. into the shared SQLite DB or an external store).

### Why Azure Files and not Blob Storage

The `/data` volume holds a live SQLite database file and append-mode log
files. Blob Storage mounted via blobfuse has weaker locking/consistency
guarantees than a real filesystem, which is risky for a file that's being
written to while also potentially being read. Azure Files gives POSIX-ish
semantics and is a first-class volume type for Container Apps, so it's used
instead.

## Cost estimate (rough, East US region, Aug 2026 pricing)

| Resource | Estimated monthly cost |
|---|---|
| Storage Account (static website, frontend) | <$1 |
| Container Apps (Consumption, scale-to-zero, low traffic) | ~$0-5 |
| Container Registry (Basic) | ~$5 (flat) |
| Storage Account + Files share (`/data` volume, few GB) | <$1 |
| Log Analytics (PerGB2018, 30-day retention, low volume) | ~$0-2 |
| **Total** | **~$5-10/month** |

This is an estimate, not a bill. **After the first deploy, check actual spend
in Azure Cost Management** (`az consumption` or the Cost Management + Billing
blade in the portal) — this deployment is meant to run against a limited
one-time credit (~$100), so keep an eye on it, especially Container Apps
compute if traffic/usage patterns turn out heavier than expected.

## Prerequisites

- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) installed
  and logged in: `az login`
- The Bicep CLI extension (az will offer to install it automatically the first
  time you run a command that needs it; or install explicitly: `az bicep install`)
- An Azure subscription with the credit/budget applied
- Node.js + npm (to `npm run build` the frontend in step 5 — no separate CLI
  tool needed to deploy it, unlike Azure Static Web Apps' `swa` CLI)
- [Docker](https://docs.docker.com/get-docker/) installed and running, to build
  the backend image locally in step 3. `az acr build` (a remote build via ACR
  Tasks, no local Docker needed) would be the alternative, but some
  subscription types (e.g. Azure for Students) get every ACR Tasks request
  rejected with `TasksOperationsNotAllowed` regardless of registry or region —
  see the Troubleshooting section below.

## Step-by-step: provisioning from zero

All commands below assume you're in `infra/azure/` unless noted otherwise.

### 1. Pick an environment name and create the resource group

```bash
export ENVIRONMENT_NAME=dev        # or "prod"
export RESOURCE_GROUP=rg-scrapper-$ENVIRONMENT_NAME
export LOCATION=eastus2            # see Troubleshooting below if your subscription rejects this

az group create --name "$RESOURCE_GROUP" --location "$LOCATION"
```

Note: the resource group's own location here is mostly nominal — what matters
is the `location` param in `parameters/<env>.bicepparam` (step 2), which drives
every actual resource. They don't need to match.

### 2. Deploy the infrastructure (Bicep)

This creates the static-website Storage Account, Container Apps environment +
app (pointed at a public placeholder image — nothing meaningful is running
yet), Container Registry, `/data` Storage Account + Files share, and Log
Analytics workspace, all wired together. Secrets are left empty at this point
(see step 4).

```bash
az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file main.bicep \
  --parameters "parameters/${ENVIRONMENT_NAME}.bicepparam"
```

Grab the outputs (also retrievable later with `az deployment group show`):

```bash
az deployment group show \
  --resource-group "$RESOURCE_GROUP" \
  --name main \
  --query properties.outputs
```

You'll want `acrLoginServer`, `containerAppFqdn`, `frontendUrl`, and
`staticWebsiteAccountName` from here.

### 3. Build and push the backend image, deploy it

`scripts/deploy.sh` does this for you: builds the image locally with Docker
(for `linux/amd64`, regardless of your machine's own architecture — Container
Apps only runs x86_64), pushes it to the registry, then re-runs the Bicep
deployment with the new image tag so the Container App picks it up.

```bash
./scripts/deploy.sh "$RESOURCE_GROUP" "$ENVIRONMENT_NAME"
```

(You can pass an explicit image tag as a third argument; otherwise it uses
the current short git SHA.)

### 4. Set the runtime secrets (one-time, then rotate as needed)

Generate a bcrypt hash for the operator password:

```bash
uv run python -c "from passlib.hash import bcrypt; print(bcrypt.hash('choose-a-strong-password'))"
```

Then set the secrets — kept as a separate script from `deploy.sh` on purpose,
so routine redeploys never touch them:

```bash
./scripts/set-secrets.sh "$RESOURCE_GROUP" "$ENVIRONMENT_NAME" "<bcrypt-hash-from-above>"
```

(A `SESSION_SECRET` is auto-generated with `openssl rand -hex 32` if you don't
pass one explicitly as a fourth argument. Re-running this script rotates both
secrets and restarts the app to pick them up.)

### 5. Build and deploy the frontend

Point the frontend's build at the Container App's FQDN from step 2/3's
outputs, then build:

```bash
CONTAINER_APP_FQDN=$(az containerapp show \
  --name "scrapper-${ENVIRONMENT_NAME}-api" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.configuration.ingress.fqdn" -o tsv)

cd ../../frontend
echo "VITE_API_BASE_URL=https://${CONTAINER_APP_FQDN}" > .env.production
npm ci
npm run build
```

Enable static-website mode on the Storage Account (idempotent — safe to
re-run) and upload the build to its `$web` container:

```bash
# Looked up directly by naming convention (main.bicep: 'web' + environment name +
# suffix) rather than via a deployment's outputs -- deployment names vary
# (scripts/deploy.sh uses its own timestamped name, not the CLI's "main" default
# from step 2), so relying on one specific deployment record here is fragile.
STATIC_SITE_ACCOUNT=$(az storage account list \
  --resource-group "$RESOURCE_GROUP" \
  --query "[?starts_with(name, 'web${ENVIRONMENT_NAME}')].name | [0]" -o tsv)

STATIC_SITE_KEY=$(az storage account keys list \
  --account-name "$STATIC_SITE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --query "[0].value" -o tsv)

az storage blob service-properties update \
  --account-name "$STATIC_SITE_ACCOUNT" --account-key "$STATIC_SITE_KEY" \
  --static-website --index-document index.html --404-document index.html

az storage blob upload-batch \
  --account-name "$STATIC_SITE_ACCOUNT" --account-key "$STATIC_SITE_KEY" \
  -s ./dist -d '$web' --overwrite
```

(Account-key auth, matching this infra's existing pragmatic style — see the
Container Registry admin-user note below — rather than wiring up an RBAC role
assignment for a single-operator hobby deployment.)

### 6. Verify CORS

The Container App's `CORS_ORIGINS` env var is set by Bicep to the static
website's URL automatically (`main.bicep` wires the `staticWebsite` module's
`webEndpoint` output straight into the `container-app` module, as a
single-element array — `container-app.bicep` JSON-encodes it before setting
the env var, since the backend's `Settings.cors_origins` is a `list[str]` and
pydantic-settings expects list-typed env vars to be JSON, not a bare or
comma-joined string). If you later add a custom domain in front of the static
website, redeploy Bicep with that domain added as another array element in
`main.bicep`'s `corsOrigins` expression.

## Troubleshooting: `RequestDisallowedByAzure`

If `az deployment group create` fails with every resource reporting
`"RequestDisallowedByAzure"` / *"This policy maintains a set of best
available regions where your subscription can deploy resources"*, your
subscription type restricts deployments to a subscription-specific region
allowlist — this is common on **Azure for Students** and similar restricted
subscriptions, and `eastus2` is a frequent example of a region *not* on that
list even though it's a normal default elsewhere. There's no fixed public
list of which regions are allowed; to find one that works for your
subscription:

- Check `az group list -o table` / `az resource list -o table` for a region
  where you already have real (non-empty) resource groups successfully
  deployed — that region is confirmed allowed.
- Or probe candidate regions without actually provisioning anything, via
  `az deployment group validate` (same arguments as `create`, but read-only):
  a candidate that returns no `RequestDisallowedByAzure` errors is safe to use
  in `parameters/<env>.bicepparam`'s `location`.

Once you've found an allowed region, set it as `location` in
`parameters/<env>.bicepparam` — it drives every resource in this template
uniformly.

## Troubleshooting: `TasksOperationsNotAllowed`

If `scripts/deploy.sh` (or a manual `az acr build`) fails with
`"(TasksOperationsNotAllowed) ACR Tasks requests for the registry ... are not
permitted"`, your subscription has ACR Tasks (the remote-build service behind
`az acr build`/`az acr run`) blocked outright — again common on restricted
subscription types like Azure for Students. This isn't about registry
settings or region; there's no config fix. `scripts/deploy.sh` already
sidesteps it by building the image locally with Docker and pushing it
directly (plain registry push/pull, a separate capability ACR Tasks
restrictions don't affect) — make sure Docker is installed and running, per
the Prerequisites above.

## Redeploying after code changes

- **Backend only**: `./scripts/deploy.sh "$RESOURCE_GROUP" "$ENVIRONMENT_NAME"`
  (rebuilds the image, updates the Container App; does not touch secrets or
  the frontend).
- **Frontend only**: repeat step 5.
- **Infra changes** (e.g. editing a `.bicep` file): repeat step 2; it's an
  idempotent `az deployment group create`.

## Notes / deviations

- Container Registry admin user is enabled and used for the Container App's
  registry credentials (looked up directly via `listCredentials()` inside
  `modules/container-app.bicep`, never passed through a module output). This
  is a deliberate simplification over a managed-identity + `AcrPull` role
  assignment, reasonable for a single-image, low-traffic deployment.
- `webappPasswordHash` and `sessionSecret` default to empty strings in both
  `main.bicep` and the `parameters/*.bicepparam` files. **Do not put real
  secret values in a `.bicepparam` file** — they're checked into git. Always
  set them via `scripts/set-secrets.sh`. Azure Container Apps rejects a secret
  entry with an empty value, so while these are unset,
  `modules/container-app.bicep` wires `WEBAPP_PASSWORD_HASH`/`SESSION_SECRET`
  as plain empty-string env vars instead of `secretRef`s (harmless —
  `src/scrapper_api/auth.py` already treats an empty hash as "no password
  configured, all logins fail"); `set-secrets.sh` both sets the real values
  and rewires the env vars to `secretref:` once you run it.
- The Container App's image on a from-zero deploy (step 2, before step 3 has
  ever pushed anything to the ACR) points at Microsoft's public
  `mcr.microsoft.com/k8se/quickstart:latest` placeholder rather than
  `scrapper-api:latest` — the freshly created ACR is empty, so that tag
  doesn't exist yet. `containerImageTag == 'latest'` is the sentinel for
  "no real image has been pushed"; `scripts/deploy.sh` always overrides it
  with a concrete git-SHA tag once it has actually built and pushed one.
- The Dockerfile has been built and run end-to-end against the finalized
  `src/scrapper_api` package (`docker build` succeeds, the container boots
  `uvicorn`, serves `/docs`/`/openapi.json`, and `weasyprint` imports
  correctly with the installed system libs).
