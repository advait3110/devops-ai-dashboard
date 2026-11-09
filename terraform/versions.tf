terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # For a team project, store state remotely instead of on your laptop:
  # backend "s3" {
  #   bucket       = "your-terraform-state-bucket"
  #   key          = "devops-ai-dashboard/terraform.tfstate"
  #   region       = "ap-south-1"
  #   use_lockfile = true
  # }
}

provider "aws" {
  region = var.region

  # Every resource gets these tags - makes cost tracking and clean-up easy.
  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
    }
  }
}
