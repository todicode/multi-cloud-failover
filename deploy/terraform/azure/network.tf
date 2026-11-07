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

resource "azurerm_public_ip" "standby" {
  name                = "mcf-azure-public-ip"
  location            = azurerm_resource_group.standby.location
  resource_group_name = azurerm_resource_group.standby.name
  allocation_method   = "Static"
  sku                 = "Standard"
  ip_version          = "IPv4"
  zones               = ["1", "2", "3"]

  tags = {
    Project = "multi-cloud-failover"
  }
}

resource "azurerm_network_interface" "standby" {
  name                = "mcf-azure-nic"
  location            = azurerm_resource_group.standby.location
  resource_group_name = azurerm_resource_group.standby.name

  ip_configuration {
    name                          = "primary"
    primary                       = true
    subnet_id                     = azurerm_subnet.standby.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.standby.id
  }

  tags = {
    Project = "multi-cloud-failover"
  }
}

resource "azurerm_network_interface_security_group_association" "standby" {
  network_interface_id      = azurerm_network_interface.standby.id
  network_security_group_id = azurerm_network_security_group.standby.id
}
