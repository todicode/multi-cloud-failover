resource "aws_route53_zone" "project" {
  name    = "mcf.todicode.tech"
  comment = "DNS for the multi-cloud failover project"

  tags = {
    Name    = "mcf-dns"
    Project = "multi-cloud-failover"
  }
}