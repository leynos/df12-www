variable "bucket_name" {
  description = "Name of the S3 bucket used to store OpenTofu state"
  type        = string
  default     = "df12-www-state"
  nullable    = false

  validation {
    condition     = length(trimspace(var.bucket_name)) > 0 && can(regex("^[a-z0-9.-]+$", var.bucket_name))
    error_message = "bucket_name must be a non-empty string using lowercase letters, digits, dots, and hyphens."
  }
}

variable "enable_bucket_encryption" {
  description = "Whether to enable default server-side encryption on the state bucket"
  type        = bool
  default     = true
}
