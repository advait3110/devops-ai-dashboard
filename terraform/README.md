# AWS deployment with Terraform

Creates, in your account's default VPC:

| Resource | Purpose |
|---|---|
| EC2 `t3.micro` (Amazon Linux 2023) + Elastic IP | runs the dashboard with Docker Compose |
| Security group | SSH and port 8080 only from **your** IP |
| IAM role + instance profile | read-only EC2/CloudWatch access for the dashboard's AWS panel, no access keys on disk |
| SSM Parameter (SecureString) | the Gemini API key, encrypted |
| S3 bucket | private, encrypted, versioned nightly backups (30-day expiry) |
| CloudWatch alarms (+ optional SNS e-mail) | CPU > 80 % and failed status checks; shown on the dashboard |

```bash
aws configure                      # IAM user with permissions to create the above
cd terraform
cp terraform.tfvars.example terraform.tfvars   # edit it
terraform init
terraform fmt -check && terraform validate
terraform plan -out tfplan         # review what will be created
terraform apply tfplan
# wait ~5-8 minutes for first boot, then open the dashboard_url output
terraform destroy                  # remove everything when done (avoid charges)
```

**Cost:** within the AWS Free Tier the instance, 20 GB gp3 disk and alarms are free for
eligible accounts. A public IPv4 address is billed by AWS (about USD 3.6/month), so destroy the
stack after your demo.

**Security notes:** `terraform.tfstate` contains the Gemini key in plain text, so never commit it
(it is git-ignored). For teams, use the S3 backend block in `versions.tf`.
