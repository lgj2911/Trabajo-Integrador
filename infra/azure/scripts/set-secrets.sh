#!/usr/bin/env bash
# One-time (or rotate-as-needed) secret provisioning for the Container App.
#
# Kept deliberately separate from deploy.sh: routine image redeploys must never
# touch WEBAPP_PASSWORD_HASH / SESSION_SECRET, so this script is the only place
# that writes them.
#
# Usage:
#   ./scripts/set-secrets.sh <resource-group> <environment-name> <webapp-password-hash> [session-secret]
#
# - <webapp-password-hash>: a bcrypt hash of the operator password, e.g. produced
#   with: python -c "from passlib.hash import bcrypt; print(bcrypt.hash('your-password'))"
# - [session-secret]: a long random string used to sign session cookies. If
#   omitted, a fresh one is generated with `openssl rand -hex 32`.
#
# Container Apps in single-revision mode does not automatically start a new
# revision just because a secret value changed, so this script restarts the
# latest revision at the end to make sure the new values actually take effect.

set -euo pipefail

RESOURCE_GROUP="${1:?Usage: set-secrets.sh <resource-group> <environment-name> <webapp-password-hash> [session-secret]}"
ENVIRONMENT_NAME="${2:?Usage: set-secrets.sh <resource-group> <environment-name> <webapp-password-hash> [session-secret]}"
WEBAPP_PASSWORD_HASH="${3:?Usage: set-secrets.sh <resource-group> <environment-name> <webapp-password-hash> [session-secret]}"
SESSION_SECRET="${4:-$(openssl rand -hex 32)}"

CONTAINER_APP_NAME="scrapper-${ENVIRONMENT_NAME}-api"

echo "==> Setting secrets on $CONTAINER_APP_NAME"
az containerapp secret set \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --secrets \
    "webapp-password-hash=${WEBAPP_PASSWORD_HASH}" \
    "session-secret=${SESSION_SECRET}"

echo "==> Restarting the latest revision so it picks up the new secret values"
LATEST_REVISION="$(az containerapp revision list \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query "sort_by([], &properties.createdTime)[-1].name" -o tsv)"

az containerapp revision restart \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --revision "$LATEST_REVISION"

echo "==> Done. Secrets are set; the app has been restarted to pick them up."
