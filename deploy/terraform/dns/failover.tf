resource "aws_route53_record" "app_primary" {
  zone_id = aws_route53_zone.project.zone_id
  name    = "app.${aws_route53_zone.project.name}"
  type    = "CNAME"
  ttl     = 30
  records = [aws_route53_record.aws_origin.fqdn]

  set_identifier  = "aws-primary"
  health_check_id = aws_route53_health_check.aws_writer.id

  failover_routing_policy {
    type = "PRIMARY"
  }
}

resource "aws_route53_record" "app_secondary" {
  zone_id = aws_route53_zone.project.zone_id
  name    = "app.${aws_route53_zone.project.name}"
  type    = "CNAME"
  ttl     = 30
  records = [aws_route53_record.azure_origin.fqdn]

  set_identifier  = "azure-secondary"
  health_check_id = aws_route53_health_check.azure_writer.id

  failover_routing_policy {
    type = "SECONDARY"
  }
}