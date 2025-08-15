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

variable "environment" {
  description = "Deployment environment identifier"
  type        = string
  nullable    = false

  validation {
    condition     = length(var.environment) > 0 && can(regex("^[a-z0-9-]+$", var.environment))
    error_message = "Environment must be a non-empty slug using lowercase letters, digits, and hyphens."
  }
}

variable "github_owner" {
  description = "GitHub organization or user that owns the repository"
  type        = string
  nullable    = false

  validation {
    condition     = trimspace(var.github_owner) != ""
    error_message = "github_owner must not be empty or whitespace"
  }
}

variable "github_repo" {
  description = "Repository name containing the site content"
  type        = string
  nullable    = false

  validation {
    condition     = trimspace(var.github_repo) != ""
    error_message = "github_repo must not be empty or whitespace"
  }
}

variable "github_branch" {
  description = "Git branch to deploy from"
  type        = string
  default     = "main"

  validation {
    condition     = trimspace(var.github_branch) != ""
    error_message = "github_branch must not be empty or whitespace"
  }
}

variable "github_token" {
  description = "Personal access token for GitHub API"
  type        = string
  sensitive   = true
  default     = ""
}

variable "site_path" {
  description = "Local path containing site files"
  type        = string
  default     = "site"
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
