// Storage Account + Azure Files share used as the Container App's persistent /data
// volume. Azure Files (not Blob/blobfuse) is used deliberately: the backend keeps a
// SQLite database and append-mode log files on this volume, and blobfuse's weaker
// locking/consistency guarantees are risky for that access pattern. Azure Files
// gives POSIX-ish semantics that Container Apps supports natively as a volume type.
@description('Azure region for the storage account.')
param location string

@description('Globally-unique storage account name (lowercase letters/numbers, 3-24 chars).')
@minLength(3)
@maxLength(24)
param storageAccountName string

@description('Name of the Azure Files share that will be mounted at /data.')
param fileShareName string = 'scrapper-data'

@description('Quota, in GiB, for the file share. Small default since the corpus + SQLite DB is a few GB at most.')
param fileShareQuotaGiB int = 20

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    largeFileSharesState: 'Enabled'
  }
}

resource fileServices 'Microsoft.Storage/storageAccounts/fileServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource fileShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-01-01' = {
  parent: fileServices
  name: fileShareName
  properties: {
    shareQuota: fileShareQuotaGiB
    enabledProtocols: 'SMB'
  }
}

@description('Name of the storage account (the container-app module looks up its access key directly via listKeys()).')
output storageAccountName string = storageAccount.name

@description('Name of the file share to mount as the Container App\'s /data volume.')
output fileShareName string = fileShare.name
