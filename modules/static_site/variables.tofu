variable "domain_name" {
  description = "Fully qualified domain name for the site"
  type        = string
  nullable    = false

  validation {
    condition = (
      length(var.domain_name) > 0 &&
      can(regex("^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?[.])+[a-zA-Z]{2,}$", var.domain_name)) &&
      endswith(var.domain_name, var.root_domain)
    )
    error_message = "Domain name must be a valid hostname and subdomain of root_domain"
  }
}

variable "root_domain" {
  description = "Root domain used for DNS validation"
  type        = string
  nullable    = false

  validation {
    condition = (
      length(var.root_domain) > 0 &&
      can(regex("^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?[.])+[a-zA-Z]{2,}$", var.root_domain))
    )
    error_message = "Root domain must be a valid hostname"
  }
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
  description = "KMS key identifier for SSE-KMS. When sse_algorithm is 'aws:kms', supply one of: Key ID (UUID), Key ARN, Alias ARN or Alias name (alias/...); otherwise leave null."
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
