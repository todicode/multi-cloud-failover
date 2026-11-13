resource "aws_iam_role" "certbot" {
  name = "mcf-aws-certbot"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "sts:AssumeRole"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name    = "mcf-aws-certbot"
    Project = "multi-cloud-failover"
  }
}

resource "aws_iam_role_policy" "certbot_route53" {
  name = "mcf-certbot-route53"
  role = aws_iam_role.certbot.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "route53:ListHostedZones"
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = "route53:GetChange"
        Resource = "arn:aws:route53:::change/*"
      },
      {
        Effect   = "Allow"
        Action   = "route53:ChangeResourceRecordSets"
        Resource = "arn:aws:route53:::hostedzone/${var.dns_zone_id}"
        Condition = {
          "ForAllValues:StringEquals" = {
            "route53:ChangeResourceRecordSetsRecordTypes" = ["TXT"]
          }
          Null = {
            "route53:ChangeResourceRecordSetsRecordTypes" = "false"
          }
        }
      }
    ]
  })
}

resource "aws_iam_instance_profile" "certbot" {
  name = "mcf-aws-certbot"
  role = aws_iam_role.certbot.name

  tags = {
    Name    = "mcf-aws-certbot"
    Project = "multi-cloud-failover"
  }
}