variable "bucket_name" {
  description = "Name of the S3 bucket hosting the site"
  type        = string
  nullable    = false

  validation {
    condition = (
      length(trimspace(var.bucket_name)) >= 3 &&
      length(trimspace(var.bucket_name)) <= 63 &&
      can(regex("^[a-z0-9][a-z0-9.-]*[a-z0-9]$", trimspace(var.bucket_name))) &&
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
  description = "Name of the repository to deploy"
  type        = string
  nullable    = false

  validation {
    condition     = trimspace(var.github_repo) != ""
    error_message = "github_repo must not be empty or whitespace"
  }
}

variable "github_branch" {
  description = "Branch containing site content"
  type        = string
  nullable    = false

  validation {
    condition     = trimspace(var.github_branch) != ""
    error_message = "github_branch must not be empty or whitespace"
  }
}

variable "github_token" {
  description = "Personal access token used for authenticated git (HTTPS) clones"
  type        = string
  default     = ""
  sensitive   = true
}

variable "github_ssh_private_key" {
  description = "PEM-formatted private key used for SSH clones when github_token is empty"
  type        = string
  default     = ""
  sensitive   = true
}

variable "github_known_hosts" {
  description = "Optional known_hosts entries for GitHub; leave empty to run ssh-keyscan at runtime"
  type        = string
  default     = ""
}

variable "site_path" {
  description = "Path to the built static site directory within the repository"
  type        = string
  default     = "public"
  validation {
    condition     = trimspace(var.site_path) != ""
    error_message = "site_path must not be empty or whitespace"
  }
}
