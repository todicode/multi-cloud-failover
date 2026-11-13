output "dns_zone_id" {
  description = "Route 53 hosted zone ID for the project"
  value       = aws_route53_zone.project.zone_id
}

output "dns_name_servers" {
  description = "Authoritative nameservers for mcf.todicode.tech"
  value       = aws_route53_zone.project.name_servers
}