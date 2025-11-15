variable "domain_name" {
  description = "Fully qualified domain name for the site"
  type        = string
  nullable    = false

  validation {
    condition = (
      length(trimspace(var.domain_name)) > 0 &&
      can(regex("^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?[.])+[a-zA-Z]{2,}$", trimspace(var.domain_name)))
    )
    error_message = "Domain name must be a valid hostname"
  }
}

variable "root_domain" {
  description = "Root domain used for DNS validation"
  type        = string
  nullable    = false

  validation {
    condition = (
      length(trimspace(var.root_domain)) > 0 &&
      can(regex("^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?[.])+[a-zA-Z]{2,}$", trimspace(var.root_domain)))
    )
    error_message = "Root domain must be a valid hostname"
  }
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID that owns the root domain (whitespace trimmed automatically)"
  type        = string
  nullable    = false

  validation {
    condition     = length(trimspace(var.cloudflare_zone_id)) > 0 && can(regex("^[a-f0-9]{32}$", trimspace(var.cloudflare_zone_id)))
    error_message = "cloudflare_zone_id must be a 32-character hexadecimal string."
  }
}

variable "cloudflare_proxied" {
  description = "Whether Cloudflare should proxy the CDN CNAME record"
  type        = bool
  default     = false
}

variable "log_retention_days" {
  description = "Retention period in days for CloudFront logs"
  type        = number
  nullable    = false

  validation {
    condition     = var.log_retention_days >= 1 && var.log_retention_days <= 3650 && floor(var.log_retention_days) == var.log_retention_days
    error_message = "log_retention_days must be an integer between 1 and 3650."
  }
}

variable "force_destroy_logs" {
  type        = bool
  default     = false
  description = "Whether to force-destroy the logs bucket and its contents."
}

variable "force_destroy_site" {
  description = "Whether to force-destroy the primary site bucket when deleting the stack."
  type        = bool
  default     = false
}

variable "sse_algorithm" {
  description = "Server-side encryption algorithm for S3 bucket (valid values: AES256, aws:kms)"
  type        = string
  default     = "AES256"

  validation {
    condition     = contains(["AES256", "aws:kms"], var.sse_algorithm)
    error_message = "SSE algorithm must be either 'AES256' or 'aws:kms'"
  }
}

variable "sse_kms_key_id" {
  description = "KMS key identifier for SSE-KMS (Key ID UUID, Key ARN, Alias ARN, or alias/... name)."
  type        = string
  default     = null
  sensitive   = true

  validation {
    condition = var.sse_kms_key_id == null || (
      can(regex("^arn:(aws|aws-us-gov|aws-cn):kms:[a-z0-9-]+:[0-9]{12}:(key|alias)/[^\\s]+$", var.sse_kms_key_id)) ||
      can(regex("^[0-9a-fA-F-]{36}$", var.sse_kms_key_id)) ||
      can(regex("^alias/[A-Za-z0-9/_-]+$", var.sse_kms_key_id))
    )
    error_message = "When provided, sse_kms_key_id must be a Key ID (UUID), Key ARN, Alias ARN or Alias name (alias/...)."
  }
}

locals {
  domain_name_clean        = trimspace(var.domain_name)
  root_domain_clean        = trimspace(var.root_domain)
  cloudflare_zone_id_clean = trimspace(var.cloudflare_zone_id)
}
