mock_provider "aws" {}

run "plan" {
  command = plan

  variables {
    bucket_name = "df12-www-state"
  }

  assert {
    condition     = aws_s3_bucket.state.bucket == "df12-www-state"
    error_message = "state bucket name should match the provided bucket_name"
  }

  assert {
    condition     = aws_s3_bucket_versioning.state.versioning_configuration[0].status == "Enabled"
    error_message = "state bucket versioning must be enabled"
  }

  assert {
    condition     = length(aws_s3_bucket_server_side_encryption_configuration.state) == 1 && strcontains(jsonencode(aws_s3_bucket_server_side_encryption_configuration.state[0]), "\"sse_algorithm\":\"AES256\"")
    error_message = "state bucket must use AES256 server-side encryption by default"
  }

  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.state.block_public_acls,
      aws_s3_bucket_public_access_block.state.block_public_policy,
      aws_s3_bucket_public_access_block.state.ignore_public_acls,
      aws_s3_bucket_public_access_block.state.restrict_public_buckets,
    ])
    error_message = "state bucket must block all forms of public access"
  }

  assert {
    condition     = aws_s3_bucket.state.object_lock_enabled
    error_message = "state bucket must have object lock enabled"
  }

  assert {
    condition     = strcontains(jsonencode(aws_s3_bucket_object_lock_configuration.state), "\"mode\":\"GOVERNANCE\"") && strcontains(jsonencode(aws_s3_bucket_object_lock_configuration.state), "\"days\":30")
    error_message = "state bucket must enforce governance retention with 30-day default"
  }

  assert {
    condition     = strcontains(jsonencode(aws_s3_bucket_lifecycle_configuration.state), "\"storage_class\":\"GLACIER_IR\"") && strcontains(jsonencode(aws_s3_bucket_lifecycle_configuration.state), "\"noncurrent_days\":30")
    error_message = "state bucket must transition noncurrent versions to Glacier after 30 days"
  }

  assert {
    condition     = strcontains(jsonencode(aws_s3_bucket_lifecycle_configuration.state), "\"noncurrent_days\":365")
    error_message = "state bucket must expire noncurrent versions after 365 days"
  }
}
