variable "project" {
  description = "Name prefix for all resources"
  type        = string
  default     = "devops-ai"
}

variable "region" {
  description = "AWS region (ap-south-1 = Mumbai)"
  type        = string
  default     = "ap-south-1"
}

variable "instance_type" {
  description = "EC2 size. t3.micro is Free Tier eligible in most regions (1 GB RAM)."
  type        = string
  default     = "t3.micro"
}

variable "allowed_cidr" {
  description = "Your public IP in CIDR form, e.g. 203.0.113.10/32. Only this address can reach SSH (and Grafana/Prometheus)."
  type        = string

  validation {
    condition     = can(cidrhost(var.allowed_cidr, 0))
    error_message = "allowed_cidr must be a valid CIDR block such as 203.0.113.10/32."
  }
}

variable "ssh_public_key_path" {
  description = "Path to your SSH public key (create one with: ssh-keygen -t ed25519)"
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}

variable "repo_url" {
  description = "Git URL of this project; the instance clones it on first boot"
  type        = string
}

variable "repo_branch" {
  description = "Branch to deploy"
  type        = string
  default     = "main"
}

variable "gemini_api_key" {
  description = "Google Gemini API key - stored encrypted in SSM Parameter Store, never in user-data"
  type        = string
  sensitive   = true
  default     = ""
}

variable "github_token" {
  description = "Optional GitHub token (Actions: read) so the cloud dashboard shows your pipelines - stored encrypted in SSM"
  type        = string
  sensitive   = true
  default     = ""
}

variable "domain_name" {
  description = "Optional domain pointing at the Elastic IP (e.g. myname.duckdns.org). Empty = HTTPS directly on the IP address."
  type        = string
  default     = ""
}

variable "site_username" {
  description = "Login name for the public website (HTTP basic auth in Caddy)"
  type        = string
  default     = "admin"
}

variable "site_password" {
  description = "Password for the public website - stored encrypted in SSM, hashed with bcrypt on the server"
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.site_password) >= 8
    error_message = "site_password must be at least 8 characters."
  }
}

variable "enable_monitoring_stack" {
  description = "Also start Prometheus, Grafana and node-exporter on the instance (needs ~450 MB more RAM; use t3.small)"
  type        = bool
  default     = false
}

variable "alarm_email" {
  description = "Optional e-mail address for CloudWatch alarm notifications (confirm the subscription e-mail)"
  type        = string
  default     = ""
}
