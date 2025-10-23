output "delivery_hostname" {
  description = "Hostname serving the site content"
  value       = local.use_scaleway ? module.site_scaleway[0].website_endpoint : module.site_aws[0].cloudfront_domain
}

output "site_url" {
  description = "Primary URL for the site"
  value       = "https://${var.domain_name}"
}
