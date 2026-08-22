// Container Apps Environment + Container App running the FastAPI backend.
//
// *** MAX REPLICAS IS HARD-CODED TO 1. DO NOT PARAMETERIZE THIS UP. ***
// The backend keeps in-process job-queue state and a session manager in memory
// (see src/scrapper_api). Running more than one replica would let requests land on
// different instances with different in-memory state, silently corrupting
// behavior (not just wasting money) rather than failing loudly. If this service
// ever needs horizontal scale, that state must move to the shared DATA_DIR/SQLite
// (or an external store) *first*.
@description('Azure region for the environment and container app.')
param location string

@description('Name of the Container Apps managed environment.')
param environmentName string

@description('Name of the container app.')
param containerAppName string

@description('Name of the existing Log Analytics workspace to wire into the environment\'s log destination.')
param logAnalyticsWorkspaceName string

@description('Name of the existing storage account backing the /data Azure Files mount.')
param storageAccountName string

@description('Name of the existing Azure Files share to mount at /data.')
param fileShareName string

@description('Name of the existing Azure Container Registry the image is pulled from.')
param acrRegistryName string

@description('Tag of the scrapper-api image to deploy, e.g. the git SHA pushed by `az acr build`.')
param containerImageTag string = 'latest'

@description('Non-secret username for the single web-app operator account.')
param webappUsername string = 'admin'

@description('Bcrypt hash of the operator password. Left empty on initial provisioning; set for real via scripts/set-secrets.sh, never via a checked-in parameter file.')
@secure()
param webappPasswordHash string = ''

@description('Secret used to sign session cookies. Left empty on initial provisioning; set for real via scripts/set-secrets.sh, never via a checked-in parameter file.')
@secure()
param sessionSecret string = ''

@description('Comma-separated list of allowed CORS origins (must include the Static Web App\'s https URL).')
param corsOrigins string

@description('Minimum replica count. 0 enables scale-to-zero for cost; a cold start will incur request latency on the next call.')
param minReplicas int = 0

// Hard requirement — see the module-level comment above. Intentionally not a
// param: this must not be overridable from a parameters file.
var maxReplicas = 1

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: logAnalyticsWorkspaceName
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: storageAccountName
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrRegistryName
}

resource environment 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: environmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsWorkspace.properties.customerId
        sharedKey: logAnalyticsWorkspace.listKeys().primarySharedKey
      }
    }
  }
}

resource environmentStorage 'Microsoft.App/managedEnvironments/storages@2023-05-01' = {
  parent: environment
  name: 'scrapper-data-storage'
  properties: {
    azureFile: {
      accountName: storageAccount.name
      accountKey: storageAccount.listKeys().keys[0].value
      shareName: fileShareName
      accessMode: 'ReadWrite'
    }
  }
}

resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: containerAppName
  location: location
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acr.listCredentials().passwords[0].value
        }
        {
          name: 'webapp-password-hash'
          value: webappPasswordHash
        }
        {
          name: 'session-secret'
          value: sessionSecret
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'scrapper-api'
          image: '${acr.properties.loginServer}/scrapper-api:${containerImageTag}'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'DATA_DIR'
              value: '/data'
            }
            {
              name: 'WEBAPP_USERNAME'
              value: webappUsername
            }
            {
              name: 'WEBAPP_PASSWORD_HASH'
              secretRef: 'webapp-password-hash'
            }
            {
              name: 'SESSION_SECRET'
              secretRef: 'session-secret'
            }
            {
              name: 'CORS_ORIGINS'
              value: corsOrigins
            }
          ]
          volumeMounts: [
            {
              volumeName: 'data'
              mountPath: '/data'
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'data'
          storageType: 'AzureFile'
          storageName: environmentStorage.name
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

@description('Fully-qualified domain name of the deployed Container App, e.g. <app>.<random>.<region>.azurecontainerapps.io.')
output fqdn string = containerApp.properties.configuration.ingress.fqdn

@description('Name of the container app, used by scripts/deploy.sh and scripts/set-secrets.sh.')
output containerAppName string = containerApp.name
