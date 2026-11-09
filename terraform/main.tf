# ---------------------------------------------------------------------
# Network + EC2 instance that runs the dashboard with Docker Compose.
# Uses the account's default VPC so no NAT gateway (which costs money)
# is created.
# ---------------------------------------------------------------------

data "aws_vpc" "default" {
  default = true
}

# Latest Amazon Linux 2023 AMI, looked up at plan time (no hard-coded AMI id).
data "aws_ssm_parameter" "al2023" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_key_pair" "this" {
  key_name   = "${var.project}-key"
  public_key = file(pathexpand(var.ssh_public_key_path))
}

resource "aws_security_group" "dashboard" {
  name        = "${var.project}-sg"
  description = "DevOps AI Dashboard: SSH and web only from the owner's IP"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_cidr]
  }

  ingress {
    description = "Dashboard (Nginx)"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = [var.allowed_cidr]
  }

  dynamic "ingress" {
    for_each = var.enable_monitoring_stack ? { grafana = 3000, prometheus = 9090 } : {}
    content {
      description = ingress.key
      from_port   = ingress.value
      to_port     = ingress.value
      protocol    = "tcp"
      cidr_blocks = [var.allowed_cidr]
    }
  }

  egress {
    description = "All outbound (package installs, Gemini API, GitHub)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "dashboard" {
  ami                    = data.aws_ssm_parameter.al2023.value
  instance_type          = var.instance_type
  key_name               = aws_key_pair.this.key_name
  vpc_security_group_ids = [aws_security_group.dashboard.id]
  iam_instance_profile   = aws_iam_instance_profile.dashboard.name

  # IMDSv2 only (protects instance credentials from SSRF).
  # hop limit 2 lets the backend CONTAINER reach the metadata service for its IAM role.
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  root_block_device {
    volume_size           = 20 # GB, Free Tier allows up to 30
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    repo_url          = var.repo_url
    repo_branch       = var.repo_branch
    region            = var.region
    gemini_param      = aws_ssm_parameter.gemini_key.name
    backup_bucket     = aws_s3_bucket.backups.bucket
    enable_monitoring = var.enable_monitoring_stack
  })
  user_data_replace_on_change = true

  tags = {
    Name = "${var.project}-server"
  }
}

resource "aws_eip" "dashboard" {
  instance = aws_instance.dashboard.id
  domain   = "vpc"
  tags     = { Name = "${var.project}-ip" }
}
