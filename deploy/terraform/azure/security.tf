resource "azurerm_network_security_group" "standby" {
  name                = "mcf-azure-nsg"
  location            = azurerm_resource_group.standby.location
  resource_group_name = azurerm_resource_group.standby.name

  tags = {
    Project = "multi-cloud-failover"
  }
}

resource "azurerm_network_security_rule" "ssh" {
  name                        = "ssh-from-operator"
  priority                    = 300
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "22"
  source_address_prefix       = var.admin_cidr
  destination_address_prefix  = "*"
  resource_group_name         = azurerm_resource_group.standby.name
  network_security_group_name = azurerm_network_security_group.standby.name
}

resource "azurerm_network_security_rule" "http" {
  name                        = "http-from-internet"
  priority                    = 310
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "80"
  source_address_prefix       = "Internet"
  destination_address_prefix  = "*"
  resource_group_name         = azurerm_resource_group.standby.name
  network_security_group_name = azurerm_network_security_group.standby.name
}

resource "azurerm_network_security_rule" "https" {
  name                        = "https-from-internet"
  priority                    = 320
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "Internet"
  destination_address_prefix  = "*"
  resource_group_name         = azurerm_resource_group.standby.name
  network_security_group_name = azurerm_network_security_group.standby.name
}
