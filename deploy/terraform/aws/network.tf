resource "aws_vpc" "primary" {
  cidr_block           = "10.29.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name    = "mcf-aws-vpc"
    Project = "multi-cloud-failover"
  }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.primary.id
  cidr_block              = "10.29.1.0/24"
  availability_zone       = "ap-southeast-1c"
  map_public_ip_on_launch = false

  tags = {
    Name    = "mcf-aws-public-subnet"
    Project = "multi-cloud-failover"
  }
}

resource "aws_internet_gateway" "primary" {
  vpc_id = aws_vpc.primary.id

  tags = {
    Name    = "mcf-aws-igw"
    Project = "multi-cloud-failover"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.primary.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.primary.id
  }

  tags = {
    Name    = "mcf-aws-public-rt"
    Project = "multi-cloud-failover"
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}
