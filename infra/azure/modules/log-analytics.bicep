// Log Analytics workspace, required by the Container Apps managed environment for
// system/console log collection. Kept on the cheapest viable tier with a short
// retention window since this is a low-traffic hobby/demo deployment.
@description('Azure region for the workspace.')
param location string

@description('Name of the Log Analytics workspace.')
param workspaceName string

@description('Log retention in days. Kept short to minimize ingestion/retention cost.')
param retentionInDays int = 30

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: retentionInDays
    features: {
      disableLocalAuth: false
    }
  }
}

@description('Resource ID of the workspace, used to link the Container Apps environment.')
output workspaceId string = workspace.id

@description('Customer ID (workspace ID GUID) required by the Container Apps environment.')
output customerId string = workspace.properties.customerId

@description('Name of the workspace, used to look up its shared key from the container-app module.')
output workspaceName string = workspace.name
