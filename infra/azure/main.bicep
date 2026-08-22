// Top-level deployment for the Classiflow/Rosario scraper web app on Azure.
//
// Scope: resource group. Deploy with:
//   az deployment group create --resource-group <rg> --template-file main.bicep \
//     --parameters parameters/<env>.bicepparam
//
// Wires together: Log Analytics -> Container Apps Environment -> Container App
// (backend, Consumption plan, scale 0-1 — see modules/container-app.bicep for why
// max replicas is hard-capped at 1), Storage Account + Azure Files share (the
// Container App's /data volume), Container Registry (Basic), and a Static Web App
// (Free tier, frontend). See infra/azure/README.md for the full walkthrough.
targetScope = 'resourceGroup'

@description('Short environment name used to derive resource names, e.g. \'dev\' or \'prod\'.')
@minLength(2)
@maxLength(10)
param environmentName string

@description('Azure region for most resources (Container Apps, ACR, Storage, Log Analytics).')
param location string = resourceGroup().location

@description('Azure region for the Static Web App. Free tier is only available in a limited set of regions (eastus2, centralus, westus2, westeurope, eastasia) which may differ from `location`.')
param staticWebAppLocation string = 'eastus2'

@description('Tag of the scrapper-api image to deploy, e.g. the git SHA pushed by `az acr build` via scripts/deploy.sh.')
param containerImageTag string = 'latest'

@description('Non-secret username for the single web-app operator account.')
param webappUsername string = 'admin'

@description('Bcrypt hash of the operator password. Leave the default empty on first provisioning and set the real value afterwards with scripts/set-secrets.sh — never commit a real hash in a parameters file.')
@secure()
param webappPasswordHash string = ''

@description('Secret used to sign session cookies. Leave the default empty on first provisioning and set the real value afterwards with scripts/set-secrets.sh — never commit a real secret in a parameters file.')
@secure()
param sessionSecret string = ''

// Deterministic suffix so storage account / ACR / Static Web App names (which must
// be globally unique) don't collide across subscriptions while staying stable
// across redeploys of the same resource group + environmentName.
var uniqueSuffix = uniqueString(resourceGroup().id, environmentName)
var namePrefix = 'scrapper-${environmentName}'

// Storage account names: lowercase alphanumeric only, <= 24 chars.
var storageAccountName = take(toLower(replace('st${environmentName}${uniqueSuffix}', '-', '')), 24)
// ACR names: alphanumeric only, <= 50 chars.
var acrName = take(toLower(replace('acr${environmentName}${uniqueSuffix}', '-', '')), 50)
var staticWebAppName = '${namePrefix}-web-${uniqueSuffix}'
var logAnalyticsName = '${namePrefix}-logs'
var containerAppEnvName = '${namePrefix}-env'
var containerAppName = '${namePrefix}-api'
var fileShareName = 'scrapper-data'

module logAnalytics 'modules/log-analytics.bicep' = {
  name: 'log-analytics'
  params: {
    location: location
    workspaceName: logAnalyticsName
  }
}

module storage 'modules/storage-account.bicep' = {
  name: 'storage'
  params: {
    location: location
    storageAccountName: storageAccountName
    fileShareName: fileShareName
  }
}

module registry 'modules/container-registry.bicep' = {
  name: 'registry'
  params: {
    location: location
    registryName: acrName
  }
}

module staticWebApp 'modules/static-web-app.bicep' = {
  name: 'static-web-app'
  params: {
    location: staticWebAppLocation
    staticWebAppName: staticWebAppName
  }
}

module containerApp 'modules/container-app.bicep' = {
  name: 'container-app'
  params: {
    location: location
    environmentName: containerAppEnvName
    containerAppName: containerAppName
    logAnalyticsWorkspaceName: logAnalytics.outputs.workspaceName
    storageAccountName: storage.outputs.storageAccountName
    fileShareName: storage.outputs.fileShareName
    acrRegistryName: registry.outputs.registryName
    containerImageTag: containerImageTag
    webappUsername: webappUsername
    webappPasswordHash: webappPasswordHash
    sessionSecret: sessionSecret
    // The backend's CORS allow-list must include the Static Web App's origin so
    // the frontend (a different origin) can call it.
    corsOrigins: 'https://${staticWebApp.outputs.hostname}'
    minReplicas: 0
  }
}

@description('Default hostname of the Static Web App (frontend).')
output staticWebAppHostname string = staticWebApp.outputs.hostname

@description('Fully-qualified domain name of the Container App (backend API). Use this to set VITE_API_BASE_URL before building the frontend.')
output containerAppFqdn string = containerApp.outputs.fqdn

@description('Login server of the Container Registry, used by scripts/deploy.sh to push images.')
output acrLoginServer string = registry.outputs.loginServer
