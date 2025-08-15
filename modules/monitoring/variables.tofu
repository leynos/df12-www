variable "domain_name" {
  description = "Fully qualified domain name for monitoring dashboard"
  type        = string
  nullable    = false

  validation {
    condition = (
      length(var.domain_name) > 0 &&
      can(regex("^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?[.])+[a-zA-Z]{2,}$", var.domain_name)) &&
      length(format("%s-%s-visitors", replace(var.domain_name, ".", "-"), var.environment)) <= 255
    )
    error_message = "Domain name must be a valid hostname and yield dashboard name <= 255 characters"
  }
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

variable "bucket_name" {
  description = "Name of the S3 bucket storing site content"
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]*[a-z0-9]$", var.bucket_name)) && length(var.bucket_name) >= 3 && length(var.bucket_name) <= 63
    error_message = "Bucket name must be a valid S3 bucket name (3-63 characters, lowercase letters, numbers, dots, hyphens)"
  }
}

variable "distribution_id" {
  description = "ID of the CloudFront distribution"
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^E[A-Z0-9]{13}$", var.distribution_id))
    error_message = "Distribution ID must be a valid CloudFront distribution identifier (starts with 'E' followed by 13 uppercase alphanumeric characters)"
  }
}

variable "budget_limit_gbp" {
  description = "Monthly cost limit that triggers alerts, in GBP"
  type        = number
  nullable    = false

  validation {
    condition     = var.budget_limit_gbp > 0
    error_message = "Budget limit must be a positive number"
  }
}

variable "budget_email" {
  description = "Email address for budget notifications"
  type        = string
  nullable    = false

  validation {
    condition     = trimspace(var.budget_email) != "" && can(regex("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", trimspace(var.budget_email)))
    error_message = "Budget email must be a valid email address"
  }
}
