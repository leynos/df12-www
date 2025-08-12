variable "domain_name" {
  description = "Fully qualified domain name for monitoring dashboard"
  type        = string
  nullable    = false

  validation {
    condition     = length(var.domain_name) > 0 && can(regex("^([a-zA-Z0-9-]+\\.)+[a-zA-Z]{2,}$", var.domain_name))
    error_message = "Domain name must be a valid non-empty hostname"
  }
}

variable "bucket_name" {
  description = "Name of the S3 bucket storing site content"
  type        = string
  nullable    = false
}

variable "distribution_id" {
  description = "ID of the CloudFront distribution"
  type        = string
  nullable    = false
}

variable "budget_limit_gbp" {
  description = "Monthly cost limit that triggers alerts, in GBP"
  type        = number
  nullable    = false
}

variable "budget_email" {
  description = "Email address for budget notifications"
  type        = string
  nullable    = false
}
