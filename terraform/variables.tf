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
  description = "Your public IP in CIDR form, e.g. 203.0.113.10/32. Only this address can reach SSH and the dashboard."
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
