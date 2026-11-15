resource "aws_iam_user" "watcher" {
  name = "mcf-azure-watcher"

  tags = {
    Name    = "mcf-azure-watcher"
    Project = "multi-cloud-failover"
  }
}

resource "aws_iam_user_policy" "watcher_observe" {
  name = "mcf-watcher-observe"
  user = aws_iam_user.watcher.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ec2:DescribeInstances"
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = "route53:GetHealthCheckStatus"
        Resource = "arn:aws:route53:::healthcheck/${var.aws_writer_health_check_id}"
      }
    ]
  })
}