output "public_ip" {
  description = "Elastic IP of the dashboard server"
  value       = local.public_ip
}

output "dashboard_url" {
  description = "Public HTTPS website (log in with site_username / site_password)"
  value       = local.site_url
}

output "site_username" {
  value = var.site_username
}

output "grafana_url" {
  value = var.enable_monitoring_stack ? "${local.site_url}/grafana/" : "monitoring stack disabled"
}

output "ssh_command" {
  value = "ssh ec2-user@${local.public_ip}"
}

output "backup_bucket" {
  value = aws_s3_bucket.backups.bucket
}

output "first_boot_log" {
  description = "Follow the installation progress after 'apply'"
  value       = "ssh ec2-user@${local.public_ip} sudo tail -f /var/log/devops-ai-setup.log"
}
