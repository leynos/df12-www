variable "bucket_name" {
  description = "Name of the Scaleway object storage bucket"
  type        = string
  nullable    = false
}

variable "bucket_region" {
  description = "Scaleway region hosting the bucket"
  type        = string
  nullable    = false
}

variable "github_owner" {
  description = "GitHub organization or user"
  type        = string
  nullable    = false
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
  nullable    = false
}

variable "github_branch" {
  description = "Branch containing the site content"
  type        = string
  nullable    = false
}

variable "github_token" {
  description = "GitHub personal access token"
  type        = string
  default     = ""
  sensitive   = true
}

variable "github_ssh_private_key" {
  description = "PEM-formatted private key for SSH git clones (optional alternative to github_token)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "github_known_hosts" {
  description = "Optional known_hosts entries for GitHub; when empty the deploy module runs ssh-keyscan github.com"
  type        = string
  default     = ""
}

variable "site_path" {
  description = "Relative path to the built site"
  type        = string
  default     = "public"
}

variable "scaleway_access_key" {
  description = "Scaleway API access key used for object storage uploads"
  type        = string
  nullable    = false
  sensitive   = true
}

variable "scaleway_secret_key" {
  description = "Scaleway API secret key used for object storage uploads"
  type        = string
  nullable    = false
  sensitive   = true
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token with cache purge permissions"
  type        = string
  nullable    = false
  sensitive   = true
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID to purge after deployments"
  type        = string
  nullable    = false
}
