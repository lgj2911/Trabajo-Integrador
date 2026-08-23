// Storage Account hosting the built Vite/React frontend (frontend/dist) via Blob
// static website hosting (the `$web` container), instead of Azure Static Web Apps.
// SWA's Free tier only exists in a handful of regions (eastus2, centralus, westus2,
// westeurope, eastasia) — some subscriptions (e.g. Azure for Students) restrict
// deployments to a subscription-specific region allowlist that may not intersect
// with that list at all. A plain Storage account works in any region, so this
// avoids that constraint entirely. See infra/azure/README.md for the deploy flow.
//
// NOTE: enabling static-website mode (the `$web` container, index/404 documents)
// is a data-plane setting (`az storage blob service-properties update
// --static-website`), not an ARM/Bicep resource property — it's done once as part
// of the frontend deploy step, not here.
@description('Azure region for the storage account.')
param location string

@description('Globally-unique storage account name (lowercase letters/numbers, 3-24 chars).')
@minLength(3)
@maxLength(24)
param storageAccountName string

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    // Required for the $web container's contents to be publicly readable once
    // static-website mode is turned on.
    allowBlobPublicAccess: true
  }
}

@description('Name of the storage account (used for the static-website enable/upload commands in the README).')
output storageAccountName string = storageAccount.name

@description('Public URL the static website is served from, e.g. https://<account>.z##.web.core.windows.net (trailing slash trimmed).')
output webEndpoint string = substring(
  storageAccount.properties.primaryEndpoints.web,
  0,
  length(storageAccount.properties.primaryEndpoints.web) - 1
)
