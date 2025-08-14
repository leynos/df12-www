variable "bucket_name" {
  description = "Name of the S3 bucket hosting the site"
  type        = string
  nullable    = false

  validation {
    condition     = trimspace(var.bucket_name) != ""
    error_message = "bucket_name must not be empty or whitespace"
  }
}

variable "distribution_id" {
  description = "ID of the CloudFront distribution"
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[A-Z0-9]{14}$", var.distribution_id))
    error_message = "Distribution ID must be a valid CloudFront distribution identifier (14 uppercase alphanumeric characters)"
  }
}

variable "github_owner" {
  description = "GitHub organization or user that owns the repository"
  type        = string
  nullable    = false
}

variable "github_repo" {
  description = "Name of the repository to deploy"
  type        = string
  nullable    = false
}

variable "github_branch" {
  description = "Branch containing site content"
  type        = string
  nullable    = false
}

variable "github_token" {
  description = "Personal access token for GitHub API"
  type        = string
  nullable    = false
  sensitive   = true
}

variable "site_path" {
  description = "Path to the site directory within the repository"
  type        = string
  default     = "site"
}
