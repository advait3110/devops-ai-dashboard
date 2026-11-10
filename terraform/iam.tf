# ---------------------------------------------------------------------
# IAM: the EC2 instance gets a ROLE (temporary credentials, rotated by AWS)
# instead of access keys stored on disk. Least privilege: the dashboard can
# only READ EC2/CloudWatch/S3 metadata, read ONE SSM parameter and write
# backups to ONE bucket.
# ---------------------------------------------------------------------

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "dashboard" {
  name               = "${var.project}-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

data "aws_iam_policy_document" "dashboard" {
  statement {
    sid = "ReadInfrastructure"
    actions = [
      "ec2:DescribeInstances",
      "cloudwatch:GetMetricStatistics",
      "cloudwatch:DescribeAlarms",
      "s3:ListAllMyBuckets",
    ]
    resources = ["*"] # these Describe/List APIs do not support resource-level permissions
  }

  statement {
    sid     = "ReadSecrets"
    actions = ["ssm:GetParameter"]
    resources = [
      aws_ssm_parameter.gemini_key.arn,
      aws_ssm_parameter.github_token.arn,
      aws_ssm_parameter.site_password.arn,
    ]
  }

  statement {
    sid       = "WriteBackups"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.backups.arn, "${aws_s3_bucket.backups.arn}/*"]
  }
}

resource "aws_iam_role_policy" "dashboard" {
  name   = "${var.project}-dashboard-policy"
  role   = aws_iam_role.dashboard.id
  policy = data.aws_iam_policy_document.dashboard.json
}

# Lets you open a shell from the AWS console (Session Manager) without SSH.
resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.dashboard.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "dashboard" {
  name = "${var.project}-instance-profile"
  role = aws_iam_role.dashboard.name
}

# Secrets are stored encrypted (KMS) and fetched by the instance at boot,
# so they never appear in user-data. Note: Terraform state also contains
# them - keep terraform.tfstate private.
resource "aws_ssm_parameter" "gemini_key" {
  name        = "/${var.project}/gemini_api_key"
  description = "Google Gemini API key for the DevOps AI Dashboard"
  type        = "SecureString"
  value       = var.gemini_api_key == "" ? "not-set" : var.gemini_api_key
}

resource "aws_ssm_parameter" "github_token" {
  name        = "/${var.project}/github_token"
  description = "GitHub token (Actions read) for the DevOps AI Dashboard"
  type        = "SecureString"
  value       = var.github_token == "" ? "not-set" : var.github_token
}

resource "aws_ssm_parameter" "site_password" {
  name        = "/${var.project}/site_password"
  description = "Password of the public dashboard website"
  type        = "SecureString"
  value       = var.site_password
}
