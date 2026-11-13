resource "aws_route53_health_check" "aws_writer" {
  ip_address        = var.aws_public_ip
  fqdn              = aws_route53_record.aws_origin.fqdn
  type              = "HTTPS"
  port              = 443
  resource_path     = "/health/database"
  request_interval  = 30
  failure_threshold = 3
  enable_sni        = true

  tags = {
    Name    = "mcf-aws-writer-health"
    Project = "multi-cloud-failover"
  }
}

resource "aws_route53_health_check" "azure_writer" {
  ip_address        = var.azure_public_ip
  fqdn              = aws_route53_record.azure_origin.fqdn
  type              = "HTTPS"
  port              = 443
  resource_path     = "/health/database"
  request_interval  = 30
  failure_threshold = 3
  enable_sni        = true

  tags = {
    Name    = "mcf-azure-writer-health"
    Project = "multi-cloud-failover"
  }
}