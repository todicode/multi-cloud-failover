resource "aws_route53_record" "aws_origin" {
  zone_id = aws_route53_zone.project.zone_id
  name    = "aws.${aws_route53_zone.project.name}"
  type    = "A"
  ttl     = 60
  records = [var.aws_public_ip]
}

resource "aws_route53_record" "azure_origin" {
  zone_id = aws_route53_zone.project.zone_id
  name    = "azure.${aws_route53_zone.project.name}"
  type    = "A"
  ttl     = 60
  records = [var.azure_public_ip]
}