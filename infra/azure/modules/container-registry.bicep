// Azure Container Registry (Basic tier) storing the backend's container image.
// Admin user is enabled so the Container App can pull with a simple
// username/password credential pair (looked up directly via listCredentials() by
// the container-app module) instead of wiring up a managed identity + AcrPull role
// assignment. That's a reasonable simplification for a single-image, low-traffic
// hobby deployment; revisit if this ever needs tighter access control.
@description('Azure region for the registry.')
param location string

@description('Globally-unique registry name (alphanumeric only, 5-50 chars).')
@minLength(5)
@maxLength(50)
param registryName string

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: registryName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
}

@description('Login server hostname for the registry, e.g. <name>.azurecr.io.')
output loginServer string = registry.properties.loginServer

@description('Name of the registry, used by the container-app module to look up admin credentials.')
output registryName string = registry.name
