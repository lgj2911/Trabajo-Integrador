#!/usr/bin/env bash
# Routine (re)deploy: build+push the backend image with local Docker, deploy/update
# infrastructure via Bicep, and point the running Container App at the freshly
# built image tag.
#
# Builds locally rather than via `az acr build` (ACR Tasks) because some
# subscription types (e.g. Azure for Students) get "(TasksOperationsNotAllowed)
# ACR Tasks requests ... are not permitted" for every registry — a hard,
# subscription-level block, not something retryable or fixable via config. Local
# Docker build + `docker push` uses plain ACR push/pull instead, a separate
# capability that isn't affected by that restriction.
#
# This script never touches secrets (WEBAPP_PASSWORD_HASH / SESSION_SECRET) —
# that's scripts/set-secrets.sh's job, run once and rotated as needed, kept
# deliberately separate so routine redeploys can't accidentally clobber them.
#
# Usage:
#   ./scripts/deploy.sh <resource-group> <environment-name> [image-tag]
#
# Example:
#   ./scripts/deploy.sh rg-scrapper-dev dev git-a1b2c3d
#
# Requires: az CLI logged in (`az login`), with the Bicep extension available
# (`az bicep install` — az will offer to install it automatically on first use);
# Docker installed and running locally.

set -euo pipefail

RESOURCE_GROUP="${1:?Usage: deploy.sh <resource-group> <environment-name> [image-tag]}"
ENVIRONMENT_NAME="${2:?Usage: deploy.sh <resource-group> <environment-name> [image-tag]}"
IMAGE_TAG="${3:-$(git rev-parse --short HEAD)}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(cd "$INFRA_DIR/../.." && pwd)"

PARAMETERS_FILE="$INFRA_DIR/parameters/${ENVIRONMENT_NAME}.bicepparam"
if [[ ! -f "$PARAMETERS_FILE" ]]; then
  echo "error: no parameters file at $PARAMETERS_FILE" >&2
  echo "       (expected infra/azure/parameters/dev.bicepparam or prod.bicepparam)" >&2
  exit 1
fi

echo "==> Ensuring resource group '$RESOURCE_GROUP' exists"
az group show --name "$RESOURCE_GROUP" >/dev/null 2>&1 || {
  echo "    (not found — create it first, e.g.:"
  echo "     az group create --name '$RESOURCE_GROUP' --location eastus2)" >&2
  exit 1
}

# The registry itself must already exist (created by the bicep deploy in README
# step 2, or a previous run of this script) — looked up directly rather than
# re-deriving main.bicep's naming logic here.
echo "==> Looking up the Container Registry in '$RESOURCE_GROUP'"
ACR_NAME="$(az acr list --resource-group "$RESOURCE_GROUP" --query "[0].name" -o tsv)"
if [[ -z "$ACR_NAME" ]]; then
  echo "error: no Container Registry found in $RESOURCE_GROUP." >&2
  echo "       Run the Bicep deploy first (infra/azure/README.md step 2)." >&2
  exit 1
fi
ACR_LOGIN_SERVER="$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)"

# --platform linux/amd64: Azure Container Apps runs x86_64 only, and this may be
# built on an arm64 machine (e.g. Apple Silicon) — Docker Desktop cross-builds via
# its bundled BuildKit/QEMU without any extra setup.
echo "==> Building the image locally for linux/amd64: ${ACR_LOGIN_SERVER}/scrapper-api:${IMAGE_TAG}"
docker build \
  --platform linux/amd64 \
  -f "$INFRA_DIR/Dockerfile" \
  -t "${ACR_LOGIN_SERVER}/scrapper-api:${IMAGE_TAG}" \
  "$REPO_ROOT"

echo "==> Logging in to $ACR_LOGIN_SERVER and pushing the image"
az acr login --name "$ACR_NAME"
docker push "${ACR_LOGIN_SERVER}/scrapper-api:${IMAGE_TAG}"

echo "==> Deploying infrastructure (Bicep) — image tag '$IMAGE_TAG'"
DEPLOYMENT_NAME="scrapper-${ENVIRONMENT_NAME}-$(date +%s)"
az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file "$INFRA_DIR/main.bicep" \
  --parameters "$PARAMETERS_FILE" \
  --parameters containerImageTag="$IMAGE_TAG" \
  --name "$DEPLOYMENT_NAME"

echo "==> Done. Container App FQDN:"
az deployment group show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$DEPLOYMENT_NAME" \
  --query "properties.outputs.containerAppFqdn.value" -o tsv
