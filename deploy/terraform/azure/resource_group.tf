resource "azurerm_resource_group" "standby" {
  name     = "mcf-azure-rg"
  location = "southeastasia"

  tags = {
    Project = "multi-cloud-failover"
  }
}