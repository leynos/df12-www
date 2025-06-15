###############################################################################
#  Static Site on S3 + CloudFront + GoDaddy DNS — Parameterised OpenTofu Stack
###############################################################################

terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    godaddy-dns = {
      source  = "registry.terraform.io/veksh/godaddy-dns"
      version = ">= 0.3.12"
    }
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

provider "aws" {
  alias  = "useast1"
  region = "us-east-1"
}

provider "godaddy-dns" {
  api_key    = var.godaddy_api_key
  api_secret = var.godaddy_api_secret
}

provider "github" {
  token = var.github_token
}

variable "domain_name" {
  description = "The full domain for the site (e.g. www.example.com)"
  type        = string
  nullable    = false

  validation {
    condition     = length(var.domain_name) > 0 && can(regex("^([a-zA-Z0-9-]+\\.)+[a-zA-Z]{2,}$", var.domain_name))
    error_message = "Domain name must be a valid non-empty hostname"
  }
}

variable "root_domain" {
  description = "The apex / root domain (e.g. example.com). Used for redirect records."
  type        = string
  nullable    = false

  validation {
    condition     = length(var.root_domain) > 0 && can(regex("^([a-zA-Z0-9-]+\\.)+[a-zA-Z]{2,}$", var.root_domain))
    error_message = "Root domain must be a valid non-empty hostname"
  }
}

variable "aws_region" {
  description = "AWS region for the S3 bucket & CloudFront logs"
  type        = string
  default     = "eu-west-2"
}

variable "github_owner" {
  description = "GitHub organization or user that owns the repository"
  type        = string
  nullable    = false
}

variable "github_repo" {
  description = "Repository name containing the site content"
  type        = string
  nullable    = false
}

variable "github_branch" {
  description = "Git branch to deploy from"
  type        = string
  default     = "main"
}

variable "github_token" {
  description = "Personal access token for GitHub API"
  type        = string
  sensitive   = true
  default     = ""
}

variable "site_path" {
  type    = string
  default = "site"
}

variable "budget_limit_gbp" {
  description = "Monthly cost limit that triggers email alerts (GBP)"
  type        = number
  default     = 5
}

variable "budget_email" {
  description = "Email for budget alerts"
  type        = string
  nullable    = false
}

variable "godaddy_api_key" {
  description = "API key for GoDaddy DNS"
  type        = string
  sensitive   = true
  nullable    = false
}

variable "godaddy_api_secret" {
  description = "API secret for GoDaddy DNS"
  type        = string
  sensitive   = true
  nullable    = false
}

variable "log_retention_days" {
  description = "Retention period in days for CloudFront logs"
  type        = number
  default     = 14
}

module "site" {
  source             = "./modules/static_site"
  domain_name        = var.domain_name
  root_domain        = var.root_domain
  log_retention_days = var.log_retention_days

  providers = {
    aws         = aws
    aws.useast1 = aws.useast1
    godaddy-dns = godaddy-dns
  }
}

module "deploy" {
  source          = "./modules/deploy"
  bucket_name     = module.site.bucket_name
  distribution_id = module.site.distribution_id
  github_owner    = var.github_owner
  github_repo     = var.github_repo
  github_branch   = var.github_branch
  github_token    = var.github_token
  site_path       = var.site_path
}

module "monitoring" {
  source           = "./modules/monitoring"
  domain_name      = var.domain_name
  bucket_name      = module.site.bucket_name
  distribution_id  = module.site.distribution_id
  budget_limit_gbp = var.budget_limit_gbp
  budget_email     = var.budget_email
}

output "cloudfront_domain" {
  value = module.site.cloudfront_domain
}

output "site_url" {
  value = "https://${var.domain_name}"
}

