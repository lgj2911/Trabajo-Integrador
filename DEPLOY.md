# Deployment Guide — Municipalidad de Rosario Downloader

Two independent deployment paths exist for this repo:

- **Web app (Azure)** — the recommended path if you want a browser UI for
  triggering/monitoring scrapes and downloading results. See "Azure (web app
  hosting)" below.
- **CLI via Google Colab + Google Drive** — a manual/legacy path for running
  the raw CLI (`python -m scrapper ...`) with no server to maintain. See
  "Google Colab + Google Drive" below. Still fully supported, just no browser
  UI, execution history, or auth.

## Scale estimate

| Category | Documents |
|---|---|
| boletines | 2,035 |
| compendios | 27 |
| decretos | 5,483 |
| decretos concejo | 6,738 |
| ordenanzas | 5,306 |
| resoluciones | 173 |
| resoluciones concejo | 167 |
| convenios | 8 |
| declaraciones concejo | 37 |
| decreto-ordenanzas | 344 |
| **TOTAL** | **~20,318** |

Assuming ~200 KB average per PDF → **~4 GB** total storage.

---

## Azure (web app hosting)

The web app (`src/scrapper_api/` backend + `frontend/` React SPA) is designed
to run on Azure against a limited one-time credit (this project was built
against a ~$100 budget). Full step-by-step deployment instructions —
`az` CLI commands, secrets setup, redeploying after code changes — live in
[`infra/azure/README.md`](infra/azure/README.md). This section is the
overview; that file is the walkthrough.

### Resources provisioned

| Resource | Tier / SKU | Purpose |
|---|---|---|
| Storage Account (static website) | Standard_LRS | Hosts the built React frontend via Blob `$web` static-site hosting |
| Azure Container Apps (environment + app) | Consumption, **max 1 replica** (hard requirement — see below) | Runs the FastAPI backend container |
| Azure Container Registry | Basic | Stores the backend's Docker image |
| Storage Account + Azure Files share | Standard_LRS | Persistent `/data` volume (SQLite DB + per-session output/logs) mounted into the Container App |
| Log Analytics workspace | PerGB2018, 30-day retention | Required by the Container Apps environment |

Frontend hosting deliberately does not use Azure Static Web Apps: its Free
tier only exists in 5 regions, and some subscription types (e.g. Azure for
Students) restrict deployments to a region allowlist that may not include any
of them. A plain Storage account works in any region.

**Why max 1 replica:** the backend keeps its scrape job queue and session
state in that one process's memory (not in an external store). Running more
than one replica would silently produce wrong behavior (lost jobs,
inconsistent session state) rather than just wasting money — this is enforced
in Bicep, not just documented.

**Why Azure Files, not Blob Storage:** the `/data` volume holds a live SQLite
database and append-mode log files; Blob Storage mounted via blobfuse has
weaker locking/consistency guarantees than a real filesystem, which is risky
for that kind of write pattern. Azure Files gives POSIX-ish semantics and is a
first-class Container Apps volume type.

### Cost estimate (rough — see `infra/azure/README.md` for the up-to-date table)

| Resource | Estimated monthly cost |
|---|---|
| Storage Account (static website, frontend) | <$1 |
| Container Apps (Consumption, scale-to-zero, low traffic) | ~$0–5 |
| Container Registry (Basic) | ~$5 (flat) |
| Storage Account + Files share (`/data` volume, few GB) | <$1 |
| Log Analytics (low volume) | ~$0–2 |
| **Total** | **~$5–10/month** |

This is an estimate, not a bill — comfortably inside a ~$100 one-time credit
for many months at this usage level, but **check actual spend in Azure Cost
Management after the first deploy** rather than relying on this table alone.

### Quick start

```bash
cd infra/azure
az login
az group create --name rg-scrapper-dev --location eastus2
az deployment group create --resource-group rg-scrapper-dev \
  --template-file main.bicep --parameters parameters/dev.bicepparam
./scripts/deploy.sh rg-scrapper-dev dev
./scripts/set-secrets.sh rg-scrapper-dev dev "<bcrypt-hash-of-your-password>"
```

(If the deployment fails with `RequestDisallowedByAzure`, your subscription
restricts which region you can deploy to — see
[`infra/azure/README.md`](infra/azure/README.md#troubleshooting-requestdisallowedbyazure).)

Then build/deploy the frontend against the Container App's URL — full
details, including how to get that URL and upload `frontend/dist` to the
static website, are in [`infra/azure/README.md`](infra/azure/README.md).

---

## Google Colab + Google Drive (CLI-only, legacy/manual path)

### Advantages
- Free (a free account is enough for ~4 GB)
- Google Drive provides 15 GB free storage
- Setup in minutes

### Steps

1. Upload the CSV files to `My Drive / Rosario_Docs / Scrapper/`
2. Upload `downloader.py` to `My Drive / Rosario_Docs/`
3. Open `colab_downloader.ipynb` in Colab
4. Run cells top to bottom

### Session timeout

Free Colab sessions disconnect after ~90 minutes of inactivity. Options:

- **Recommended**: the `checkpoint.json` file saves progress — just re-run and it picks up where it left off
- **Alternative**: Colab Pro (~$10/month) supports sessions up to 24 hours
- **Anti-idle snippet**: paste this in the browser console (F12 → Console) to simulate activity:

```javascript
function keep_alive() {
  document.querySelector("colab-connect-button")?.click();
}
setInterval(keep_alive, 60000);
```
