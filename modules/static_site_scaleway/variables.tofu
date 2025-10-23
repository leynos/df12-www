variable "domain_name" {
  description = "Fully qualified domain name for the site"
  type        = string
  nullable    = false
}

variable "root_domain" {
  description = "Root domain used for DNS configuration"
  type        = string
  nullable    = false
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID for DNS records"
  type        = string
  nullable    = false
}

variable "cloudflare_proxied" {
  description = "Whether Cloudflare should proxy the CNAME"
  type        = bool
  default     = false
}

variable "scaleway_region" {
  description = "Scaleway object storage region"
  type        = string
  nullable    = false
}

variable "project_id" {
  description = "Scaleway project identifier"
  type        = string
  nullable    = false
}
