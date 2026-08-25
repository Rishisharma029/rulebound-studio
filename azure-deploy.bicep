@description('Azure region for deployment')
param location string = resourceGroup().location

@description('App Service Plan Name')
param appServicePlanName string = 'plan-rulebound-prod'

@description('App Service Web App Name')
param webAppName string = 'app-rulebound-prod-${uniqueString(resourceGroup().id)}'

@description('Microsoft Entra ID Tenant ID')
param entraTenantId string = 'common'

@description('Microsoft Entra ID Client ID')
param entraClientId string = 'rulebound-api-client'

resource appServicePlan 'Microsoft.Web/serverfarms@2022-03-01' = {
  name: appServicePlanName
  location: location
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
  properties: {
    reserved: true
  }
}

resource webApp 'Microsoft.Web/sites@2022-03-01' = {
  name: webAppName
  location: location
  properties: {
    serverFarmId: appServicePlan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      appSettings: [
        {
          name: 'REQUIRE_ENTRA_AUTH'
          value: 'true'
        }
        {
          name: 'AZURE_TENANT_ID'
          value: entraTenantId
        }
        {
          name: 'AZURE_CLIENT_ID'
          value: entraClientId
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
      ]
    }
  }
}

output webAppEndpoint string = 'https://${webApp.properties.defaultHostName}'
