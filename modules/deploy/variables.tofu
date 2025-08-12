variable "bucket_name" {
  description = "Name of the S3 bucket hosting the site"
  type        = string
  nullable    = false
}

variable "distribution_id" {
  description = "ID of the CloudFront distribution"
  type        = string
  nullable    = false
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
}

variable "site_path" {
  description = "Path to the site directory within the repository"
  type        = string
  default     = "site"
}
