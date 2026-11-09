output "public_ip" {
  description = "Elastic IP of the dashboard server"
  value       = aws_eip.dashboard.public_ip
}

output "dashboard_url" {
  value = "http://${aws_eip.dashboard.public_ip}:8080"
}

output "grafana_url" {
  value = var.enable_monitoring_stack ? "http://${aws_eip.dashboard.public_ip}:3000" : "monitoring stack disabled"
}

output "ssh_command" {
  value = "ssh ec2-user@${aws_eip.dashboard.public_ip}"
}

output "backup_bucket" {
  value = aws_s3_bucket.backups.bucket
}

output "first_boot_log" {
  description = "Follow the installation progress after 'apply'"
  value       = "ssh ec2-user@${aws_eip.dashboard.public_ip} sudo tail -f /var/log/devops-ai-setup.log"
}
