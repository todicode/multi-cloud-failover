output "azure_vm_id" {
  description = "Azure resource ID of the standby VM"
  value       = azurerm_linux_virtual_machine.standby.id
}

output "azure_private_ip" {
  description = "Private IPv4 address of the Azure standby NIC"
  value       = azurerm_network_interface.standby.private_ip_address
}

output "azure_public_ip" {
  description = "Static public IPv4 address of the Azure standby host"
  value       = azurerm_public_ip.standby.ip_address
}
