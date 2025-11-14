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

variable "project_name" {
  description = "Project name for tagging resources"
  type        = string
  default     = "df12-www"
  nullable    = false

  validation {
    condition     = length(trimspace(var.project_name)) > 0 && can(regex("^[a-z0-9-]+$", var.project_name))
    error_message = "Project name must be a non-empty lowercase alphanumeric or hyphenated slug"
  }
}

variable "state_bucket_name" {
  description = "Name of the S3 bucket that stores OpenTofu state"
  type        = string
  default     = "df12-www-state"
  nullable    = false

  validation {
    condition     = length(trimspace(var.state_bucket_name)) > 0 && can(regex("^[a-z0-9.-]+$", var.state_bucket_name))
    error_message = "state_bucket_name must be lowercase letters, digits, dots, and hyphens."
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

variable "github_ssh_private_key" {
  description = "PEM-formatted private key used for SSH cloning (leave empty to use github_token)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "github_known_hosts" {
  description = "Optional newline-delimited known_hosts entries for GitHub; if empty, ssh-keyscan github.com is used at runtime"
  type        = string
  default     = ""
}

variable "site_path" {
  description = "Local path containing the built static site (relative to the repo root)"
  type        = string
  default     = "public"
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

variable "cloudflare_api_token" {
  description = "API token with DNS edit permissions for the Cloudflare zone"
  type        = string
  sensitive   = true
  nullable    = false

  validation {
    condition     = trimspace(var.cloudflare_api_token) != ""
    error_message = "cloudflare_api_token must not be empty or whitespace"
  }
}

variable "cloudflare_zone_id" {
  description = "Identifier of the Cloudflare zone managing the root domain"
  type        = string
  nullable    = false

  validation {
    condition     = length(trimspace(var.cloudflare_zone_id)) > 0 && can(regex("^[a-f0-9]{32}$", trimspace(var.cloudflare_zone_id)))
    error_message = "cloudflare_zone_id must be a 32-character hexadecimal string"
  }
}

variable "cloudflare_proxied" {
  description = "Whether Cloudflare should proxy the CDN CNAME record"
  type        = bool
  default     = false
}

variable "cloud_provider" {
  description = "Infrastructure provider to deploy the site to (aws or scaleway)"
  type        = string
  default     = "aws"
  nullable    = false

  validation {
    condition     = contains(["aws", "scaleway"], lower(trimspace(var.cloud_provider)))
    error_message = "cloud_provider must be either 'aws' or 'scaleway'."
  }
}

variable "scaleway_access_key" {
  description = "Scaleway API access key (required when cloud_provider is scaleway)"
  type        = string
  default     = ""
  sensitive   = true
  validation {
    condition     = lower(trimspace(var.cloud_provider)) != "scaleway" || trimspace(var.scaleway_access_key) != ""
    error_message = "scaleway_access_key must be provided when cloud_provider is scaleway."
  }
}

variable "scaleway_secret_key" {
  description = "Scaleway API secret key (required when cloud_provider is scaleway)"
  type        = string
  default     = ""
  sensitive   = true
  validation {
    condition     = lower(trimspace(var.cloud_provider)) != "scaleway" || trimspace(var.scaleway_secret_key) != ""
    error_message = "scaleway_secret_key must be provided when cloud_provider is scaleway."
  }
}

variable "scaleway_project_id" {
  description = "Scaleway project ID (required when cloud_provider is scaleway)"
  type        = string
  default     = ""
  validation {
    condition     = lower(trimspace(var.cloud_provider)) != "scaleway" || trimspace(var.scaleway_project_id) != ""
    error_message = "scaleway_project_id must be provided when cloud_provider is scaleway."
  }
}

variable "scaleway_organization_id" {
  description = "Scaleway organization ID (optional when cloud_provider is scaleway)"
  type        = string
  default     = ""
}

variable "scaleway_region" {
  description = "Scaleway region for object storage (e.g. fr-par)"
  type        = string
  default     = "fr-par"
}

variable "scaleway_zone" {
  description = "Scaleway zone for services (e.g. fr-par-1)"
  type        = string
  default     = "fr-par-1"
}

variable "log_retention_days" {
  description = "Retention period in days for CloudFront logs"
  type        = number
  default     = 14
}

variable "sse_algorithm" {
  description = "Server-side encryption algorithm for the AWS static site bucket (valid values: AES256, aws:kms)"
  type        = string
  default     = "AES256"
  nullable    = false

  validation {
    condition     = contains(["AES256", "aws:kms"], var.sse_algorithm)
    error_message = "sse_algorithm must be either 'AES256' or 'aws:kms'."
  }
}

variable "sse_kms_key_id" {
  description = "Optional KMS key identifier used when sse_algorithm is 'aws:kms'. Accepts a Key ID (UUID), Key ARN, Alias ARN, or alias/... name."
  type        = string
  default     = null
  sensitive   = true

  validation {
    condition = var.sse_kms_key_id == null || (
      can(regex("^arn:(aws|aws-us-gov|aws-cn):kms:[a-z0-9-]+:[0-9]{12}:(key|alias)/[^\\s]+$", var.sse_kms_key_id)) ||
      can(regex("^[0-9a-fA-F-]{36}$", var.sse_kms_key_id)) ||
      can(regex("^alias/[A-Za-z0-9/_-]+$", var.sse_kms_key_id))
    )
    error_message = "When provided, sse_kms_key_id must be a Key ID (UUID), Key ARN, Alias ARN, or alias/... reference."
  }
}
