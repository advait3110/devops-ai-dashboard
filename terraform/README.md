# AWS deployment with Terraform

Creates, in your account's default VPC:

| Resource | Purpose |
|---|---|
| EC2 `t3.micro` (Amazon Linux 2023) + Elastic IP | runs the dashboard with Docker Compose |
| Caddy (on the instance) | the public **HTTPS** website: free Let's Encrypt certificate, http to https redirect, username/password login |
| Security group | 80/443 open to everyone (the website); SSH only from **your** IP; the app port 8088 closed |
| IAM role + instance profile | read-only EC2/CloudWatch access for the dashboard's AWS panel, no access keys on disk |
| SSM Parameters (SecureString) | Gemini key, GitHub token and site password, encrypted |
| S3 bucket | private, encrypted, versioned nightly backups (30-day expiry) |
| CloudWatch alarms (+ optional SNS e-mail) | CPU > 80 % and failed status checks; shown on the dashboard |

```bash
# credentials: run 'python aws_setup.py' in backend/ once (creates the devops-ai profile)
$env:AWS_PROFILE = "devops-ai"     # PowerShell (Linux/macOS: export AWS_PROFILE=devops-ai)
cd terraform
python make_tfvars.py              # writes terraform.tfvars from backend/.env (or copy the .example and edit)
terraform init
terraform fmt -check && terraform validate
terraform plan -out tfplan         # review what will be created
terraform apply tfplan
# wait ~10 minutes for first boot, then open the dashboard_url output (https://<elastic-ip>)
terraform destroy                  # remove everything when done (avoid charges)
```

**HTTPS without a domain:** since January 2026 Let's Encrypt issues certificates for public IP
addresses (6-day certificates from the `shortlived` profile, renewed automatically by Caddy), so
the site works as `https://<elastic-ip>` with a valid padlock. To use a name instead, create a free
subdomain (for example at duckdns.org) pointing at the Elastic IP and set `domain_name`.

**Cost:** within the AWS Free Tier the instance, 20 GB gp3 disk and alarms are free for
eligible accounts. A public IPv4 address is billed by AWS (about USD 3.6/month), so destroy the
stack after your demo.

**Security notes:** the website is public, so every visitor must log in (Caddy basic auth over
HTTPS; the password is stored in SSM and only a bcrypt hash is on disk). `terraform.tfstate` contains the secrets in plain text, so never commit it
(it is git-ignored). For teams, use the S3 backend block in `versions.tf`.
