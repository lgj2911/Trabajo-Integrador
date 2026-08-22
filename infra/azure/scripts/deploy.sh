#!/usr/bin/env bash
# Routine (re)deploy: build+push the backend image via ACR (no local Docker
# required), deploy/update infrastructure via Bicep, and point the running
# Container App at the freshly built image tag.
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
# (`az bicep install` — az will offer to install it automatically on first use).

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

echo "==> Deploying infrastructure (Bicep) — image tag '$IMAGE_TAG'"
DEPLOYMENT_NAME="scrapper-${ENVIRONMENT_NAME}-$(date +%s)"
az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --template-file "$INFRA_DIR/main.bicep" \
  --parameters "$PARAMETERS_FILE" \
  --parameters containerImageTag="$IMAGE_TAG" \
  --name "$DEPLOYMENT_NAME"

# Read the ACR login server straight back out of this deployment's outputs
# rather than re-deriving main.bicep's naming logic here.
ACR_LOGIN_SERVER="$(az deployment group show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$DEPLOYMENT_NAME" \
  --query "properties.outputs.acrLoginServer.value" -o tsv)"
ACR_NAME="${ACR_LOGIN_SERVER%%.*}"
CONTAINER_APP_NAME="scrapper-${ENVIRONMENT_NAME}-api"

echo "==> Building and pushing image to $ACR_LOGIN_SERVER (no local Docker needed)"
az acr build \
  --registry "$ACR_NAME" \
  --image "scrapper-api:${IMAGE_TAG}" \
  --file "$INFRA_DIR/Dockerfile" \
  "$REPO_ROOT"

echo "==> Pointing the Container App at scrapper-api:${IMAGE_TAG}"
az containerapp update \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --image "${ACR_LOGIN_SERVER}/scrapper-api:${IMAGE_TAG}"

echo "==> Done. Container App FQDN:"
az containerapp show \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "properties.configuration.ingress.fqdn" -o tsv
