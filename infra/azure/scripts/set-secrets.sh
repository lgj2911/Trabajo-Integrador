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
# On initial provisioning (empty webappPasswordHash/sessionSecret in the
# .bicepparam file), main.bicep's container-app module leaves WEBAPP_PASSWORD_HASH
# and SESSION_SECRET wired as plain empty-string env vars, not secretRefs -- Azure
# Container Apps rejects an empty-string secret value, so nothing can be declared
# there yet. This script both sets the secret values AND rewires the env vars to
# pull from them via `--set-env-vars ...=secretref:...`; that rewire is itself a
# template change, which reliably creates a new revision in single-revision mode
# (a secret value change alone would not), so the app always ends up running with
# the values just set -- no separate manual restart needed, on first run or rotate.

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

echo "==> Wiring WEBAPP_PASSWORD_HASH/SESSION_SECRET to pull from those secrets (triggers a new revision)"
az containerapp update \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --set-env-vars \
    "WEBAPP_PASSWORD_HASH=secretref:webapp-password-hash" \
    "SESSION_SECRET=secretref:session-secret" \
  >/dev/null

echo "==> Done. Secrets are set and the running revision picks them up."
