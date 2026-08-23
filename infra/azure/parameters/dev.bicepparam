using '../main.bicep'

param environmentName = 'dev'
// eastus: confirmed allowed by this subscription's "best available regions" policy
// (Azure for Students) — eastus2 is not. See the README's RequestDisallowedByAzure
// troubleshooting section if you're on a different subscription.
param location = 'eastus'

// Overwritten per-deploy by scripts/deploy.sh with the actual image tag being
// released (e.g. the git SHA `az acr build` just pushed).
param containerImageTag = 'latest'

param webappUsername = 'admin'

// Intentionally left empty. Real values are set once (and rotated as needed) via
// scripts/set-secrets.sh, which calls `az containerapp secret set` directly — they
// are never written to this checked-in file.
param webappPasswordHash = ''
param sessionSecret = ''
