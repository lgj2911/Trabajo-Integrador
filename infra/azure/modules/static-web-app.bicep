// Azure Static Web Apps (Free tier) hosting the built Vite/React frontend
// (frontend/dist). Deployed standalone here — no GitHub Actions integration is
// configured by this module, and no "linked backend" reverse proxy to the
// Container App is set up. The frontend is expected to call the Container App's
// FQDN directly via VITE_API_BASE_URL (baked in at build time); see the README for
// the manual `swa deploy` / deployment-token flow used to push frontend/dist here.
@description('Azure region for the Static Web App. Note: Static Web Apps Free tier is only available in a limited set of regions (e.g. eastus2, centralus, westus2, westeurope, eastasia).')
param location string

@description('Name of the Static Web App.')
param staticWebAppName string

resource staticWebApp 'Microsoft.Web/staticSites@2023-12-01' = {
  name: staticWebAppName
  location: location
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    // No repositoryUrl/branch/buildProperties: we deploy via the SWA CLI /
    // deployment token from scripts, not via a GitHub-integrated build.
    stagingEnvironmentPolicy: 'Disabled'
    allowConfigFileUpdates: true
  }
}

@description('Default hostname of the Static Web App, e.g. <random>.azurestaticapps.net.')
output hostname string = staticWebApp.properties.defaultHostname

@description('Name of the Static Web App, used to fetch its deployment token via `az staticwebapp secrets list`.')
output staticWebAppName string = staticWebApp.name
