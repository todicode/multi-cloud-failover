resource "aws_iam_user" "certbot_azure" {
  name = "mcf-azure-certbot"

  tags = {
    Name    = "mcf-azure-certbot"
    Project = "multi-cloud-failover"
  }
}

resource "aws_iam_user_policy" "certbot_azure_route53" {
  name = "mcf-certbot-route53"
  user = aws_iam_user.certbot_azure.name

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
        Resource = aws_route53_zone.project.arn
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