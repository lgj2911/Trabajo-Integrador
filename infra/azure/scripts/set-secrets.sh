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
# there yet. This script sets the secret values AND (re)wires the env vars to pull
# from them via `--set-env-vars ...=secretref:...`, forcing a brand new revision
# every time via --revision-suffix.
#
# The forced new revision is required, not cosmetic: `az containerapp secret set`
# updates the secret's stored value but explicitly warns "must be restarted for
# secret changes to take effect" -- and empirically, neither that warning's
# "restart" nor `az containerapp revision restart` on the *existing* revision
# actually re-resolves secretRef env vars against the new value. Only a genuinely
# new revision does. On the very first run, --set-env-vars is itself a template
# change (empty value -> secretRef) that creates a new revision on its own; on
# every rotation after that, the secretRef *string* is textually unchanged
# ("secretref:webapp-password-hash" both times) even though the value behind it
# changed, so Container Apps sees no template diff and silently keeps serving the
# stale revision with the old value -- this bit us in practice (secret rotated
# twice, container restarted twice, login still failed with the old password).

set -euo pipefail

RESOURCE_GROUP="${1:?Usage: set-secrets.sh <resource-group> <environment-name> <webapp-password-hash> [session-secret]}"
ENVIRONMENT_NAME="${2:?Usage: set-secrets.sh <resource-group> <environment-name> <webapp-password-hash> [session-secret]}"
WEBAPP_PASSWORD_HASH="${3:?Usage: set-secrets.sh <resource-group> <environment-name> <webapp-password-hash> [session-secret]}"
SESSION_SECRET="${4:-$(openssl rand -hex 32)}"

# A bcrypt hash always looks like $2a$/$2b$/$2y$<cost>$<53 base64 chars>, 60
# characters total. If this doesn't match, the most likely cause is passing the
# hash in double quotes on the command line -- bash expands $2b/$1 etc. as
# positional parameters inside double quotes, silently mangling the hash (e.g.
# down to a single stray character) rather than erroring, and every login then
# fails with a 500 (UnknownHashError), not a clean "wrong password". Use single
# quotes around the hash argument instead.
# (Glob match + explicit length check, not `=~` with a `{n}` interval: macOS's
# system /bin/bash is still 3.2, whose regex engine doesn't reliably support
# bounded repetition in `[[ ... =~ ... ]]`.)
if [[ "$WEBAPP_PASSWORD_HASH" != \$2[aby]\$[0-9][0-9]\$* ]] || [[ ${#WEBAPP_PASSWORD_HASH} -ne 60 ]]; then
  echo "error: '<webapp-password-hash>' doesn't look like a valid bcrypt hash." >&2
  echo "       Got: $WEBAPP_PASSWORD_HASH" >&2
  echo "       Did you wrap it in double quotes? Use single quotes instead --" >&2
  echo "       bash expands \$2b/\$1/etc. inside double quotes and silently" >&2
  echo "       mangles the hash. Re-run with: ... '<bcrypt-hash>'" >&2
  exit 1
fi

CONTAINER_APP_NAME="scrapper-${ENVIRONMENT_NAME}-api"

echo "==> Setting secrets on $CONTAINER_APP_NAME"
az containerapp secret set \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --secrets \
    "webapp-password-hash=${WEBAPP_PASSWORD_HASH}" \
    "session-secret=${SESSION_SECRET}"

echo "==> Wiring WEBAPP_PASSWORD_HASH/SESSION_SECRET to pull from those secrets, forcing a new revision"
az containerapp update \
  --name "$CONTAINER_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --set-env-vars \
    "WEBAPP_PASSWORD_HASH=secretref:webapp-password-hash" \
    "SESSION_SECRET=secretref:session-secret" \
  --revision-suffix "secrets$(date +%s)" \
  >/dev/null

echo "==> Done. New revision deployed with the values just set."
