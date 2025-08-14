variable "domain_name" {
  description = "Fully qualified domain name for the site"
  type        = string
  nullable    = false

  validation {
    condition     = length(var.domain_name) > 0 && can(regex("^([a-zA-Z0-9-]+\\.)+[a-zA-Z]{2,}$", var.domain_name))
    error_message = "Domain name must be a valid non-empty hostname"
  }
}

variable "root_domain" {
  description = "Root domain used for DNS validation"
  type        = string
  nullable    = false

  validation {
    condition     = length(var.root_domain) > 0 && can(regex("^([a-zA-Z0-9-]+\\.)+[a-zA-Z]{2,}$", var.root_domain))
    error_message = "Root domain must be a valid non-empty hostname"
  }
}

variable "log_retention_days" {
  description = "Retention period in days for CloudFront logs"
  type        = number
  nullable    = false
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
  description = "KMS key ID for server-side encryption. Required when sse_algorithm is 'aws:kms', otherwise optional."
  type        = string
  default     = null

  validation {
    condition     = var.sse_kms_key_id == null || can(regex("^[a-f0-9-]+$", var.sse_kms_key_id))
    error_message = "sse_kms_key_id must be a valid KMS key ID format when provided"
  }
}
