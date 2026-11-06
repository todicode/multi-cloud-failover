output "aws_instance_id" {
  description = "ID of the AWS primary instance"
  value       = aws_instance.primary.id
}

output "aws_private_ip" {
  description = "Private IPv4 address of the AWS primary instance"
  value       = aws_instance.primary.private_ip
}

output "aws_public_ip" {
  description = "Elastic IPv4 address of the AWS primary instance"
  value       = aws_eip.primary.public_ip
}
