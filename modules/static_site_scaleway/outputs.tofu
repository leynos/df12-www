output "bucket_name" {
  description = "Name of the Scaleway bucket hosting the site"
  value       = scaleway_object_bucket.site.name
}

output "website_endpoint" {
  description = "Public website endpoint for the bucket"
  value       = local.bucket_domain
}
