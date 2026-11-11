variable "admin_cidr" {
  description = "Public IPv4 CIDR allowed to SSH to the Azure host"
  type        = string
}

variable "wireguard_peer_cidr" {
  description = "Public IPv4 CIDR of the AWS WireGuard peer"
  type        = string
}