variable "domain_name" {
  description = "Fully qualified domain name for monitoring dashboard"
  type        = string
  nullable    = false

  validation {
    condition = (
      trimspace(var.domain_name) != "" &&
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
    condition     = trimspace(var.environment) != "" && can(regex("^[a-z0-9-]+$", trimspace(var.environment)))
    error_message = "Environment must be a non-empty slug using lowercase letters, digits, and hyphens."
  }
}

variable "bucket_name" {
  description = "Name of the S3 bucket storing site content"
  type        = string
  nullable    = false

  validation {
    condition = (
      length(trimspace(var.bucket_name)) >= 3 &&
      length(trimspace(var.bucket_name)) <= 63 &&
      can(regex("^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])$", trimspace(var.bucket_name))) &&
      !can(regex("\\.\\.", trimspace(var.bucket_name))) &&
      !can(regex("(?:\\.-|-\\.)", trimspace(var.bucket_name))) &&
      !can(regex("^\\d+\\.\\d+\\.\\d+\\.\\d+$", trimspace(var.bucket_name)))
    )
    error_message = "bucket_name must be a valid S3 bucket name"
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
