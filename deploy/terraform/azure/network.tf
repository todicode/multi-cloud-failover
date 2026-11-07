resource "azurerm_virtual_network" "standby" {
  name                = "mcf-azure-vnet"
  location            = azurerm_resource_group.standby.location
  resource_group_name = azurerm_resource_group.standby.name
  address_space       = ["10.30.0.0/16"]

  tags = {
    Project = "multi-cloud-failover"
  }
}

resource "azurerm_subnet" "standby" {
  name                 = "mcf-azure-subnet"
  resource_group_name  = azurerm_resource_group.standby.name
  virtual_network_name = azurerm_virtual_network.standby.name
  address_prefixes     = ["10.30.1.0/24"]

  default_outbound_access_enabled = false
}