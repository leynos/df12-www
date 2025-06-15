output "cloudfront_domain" {
  value = module.site.cloudfront_domain
}

output "site_url" {
  value = "https://${var.domain_name}"
}
