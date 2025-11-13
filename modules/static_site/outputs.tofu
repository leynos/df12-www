output "bucket_name" {
  description = "Name of the S3 bucket hosting the site"
  value       = aws_s3_bucket.site.bucket
}

output "distribution_id" {
  description = "CloudFront distribution ID for the site CDN"
  value       = aws_cloudfront_distribution.cdn.id
}

output "cloudfront_domain" {
  description = "CloudFront distribution domain name for the site"
  value       = aws_cloudfront_distribution.cdn.domain_name
}
