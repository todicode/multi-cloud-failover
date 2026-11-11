resource "aws_security_group" "primary" {
  name        = "mcf-aws-host"
  description = "Traffic rules for the AWS primary host"
  vpc_id      = aws_vpc.primary.id

  tags = {
    Name    = "mcf-aws-host"
    Project = "multi-cloud-failover"
  }
}

resource "aws_vpc_security_group_egress_rule" "all_ipv4" {
  security_group_id = aws_security_group.primary.id
  description       = "Allow outbound IPv4 traffic"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

resource "aws_vpc_security_group_ingress_rule" "ssh" {
  security_group_id = aws_security_group.primary.id
  description       = "Allow SSH from the operator IPv4"
  cidr_ipv4         = var.admin_cidr
  ip_protocol       = "tcp"
  from_port         = 22
  to_port           = 22
}

resource "aws_vpc_security_group_ingress_rule" "http" {
  security_group_id = aws_security_group.primary.id
  description       = "Allow public HTTP"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

resource "aws_vpc_security_group_ingress_rule" "https" {
  security_group_id = aws_security_group.primary.id
  description       = "Allow public HTTPS"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_ingress_rule" "wireguard" {
  security_group_id = aws_security_group.primary.id
  description       = "Allow WireGuard from Azure peer"
  cidr_ipv4         = var.wireguard_peer_cidr
  ip_protocol       = "udp"
  from_port         = 51820
  to_port           = 51820
}