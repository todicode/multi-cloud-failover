resource "azurerm_linux_virtual_machine" "standby" {
  name                            = "mcf-azure-standby"
  location                        = azurerm_resource_group.standby.location
  resource_group_name             = azurerm_resource_group.standby.name
  size                            = "Standard_B2als_v2"
  zone                            = "1"
  admin_username                  = "azureuser"
  disable_password_authentication = true
  network_interface_ids           = [azurerm_network_interface.standby.id]

  admin_ssh_key {
    username   = "azureuser"
    public_key = file(pathexpand("~/.ssh/mcf-lab.pub"))
  }

  os_disk {
    name                 = "mcf-azure-osdisk"
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = 32
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "24.04.202610250"
  }

  tags = {
    Project = "multi-cloud-failover"
  }

  depends_on = [azurerm_network_interface_security_group_association.standby]
}
