variable "domain_name" {
  description = "Domain monitored"
  type        = string
  nullable    = false
}

variable "bucket_name" {
  description = "Bucket serving static assets"
  type        = string
  nullable    = false
}

variable "region" {
  description = "Scaleway region"
  type        = string
  nullable    = false
}

variable "project_id" {
  description = "Scaleway project ID"
  type        = string
  nullable    = false
}

variable "alert_contacts" {
  description = "List of email contacts for alerts"
  type        = list(string)
  default     = []
}
