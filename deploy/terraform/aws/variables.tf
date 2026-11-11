variable "admin_cidr" {
  description = "Public IPv4 CIDR allowed to SSH to the AWS host"
  type        = string
}

variable "wireguard_peer_cidr" {
  description = "Public IPv4 CIDR of the Azure WireGuard peer"
  type        = string
}