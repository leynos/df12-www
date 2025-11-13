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
    condition     = aws_s3_bucket_server_side_encryption_configuration.state.rule[0].apply_server_side_encryption_by_default.sse_algorithm == "AES256"
    error_message = "state bucket must use AES256 server-side encryption by default"
  }

  assert {
    condition     = aws_s3_bucket_public_access_block.state.block_public_acls
      && aws_s3_bucket_public_access_block.state.block_public_policy
      && aws_s3_bucket_public_access_block.state.ignore_public_acls
      && aws_s3_bucket_public_access_block.state.restrict_public_buckets
    error_message = "state bucket must block all forms of public access"
  }
}

