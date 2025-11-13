output "bucket_name" {
  description = "Name of the S3 bucket storing OpenTofu state"
  value       = aws_s3_bucket.state.bucket
}

output "bucket_arn" {
  description = "ARN of the S3 bucket storing OpenTofu state"
  value       = aws_s3_bucket.state.arn
}

