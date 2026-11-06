resource "aws_key_pair" "operator" {
  key_name   = "mcf-lab"
  public_key = file(pathexpand("~/.ssh/mcf-lab.pub"))

  tags = {
    Name    = "mcf-lab"
    Project = "multi-cloud-failover"
  }
}

resource "aws_instance" "primary" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = "t3.medium"
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.primary.id]
  key_name                    = aws_key_pair.operator.key_name
  associate_public_ip_address = false

  root_block_device {
    volume_size           = 30
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = false

    tags = {
      Name    = "mcf-aws-root"
      Project = "multi-cloud-failover"
    }
  }

  credit_specification {
    cpu_credits = "standard"
  }

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  tags = {
    Name    = "mcf-aws-primary"
    Project = "multi-cloud-failover"
  }
}
