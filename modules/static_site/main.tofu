resource "aws_s3_bucket" "site" {
  bucket        = var.domain_name
  force_destroy = var.force_destroy_site
  tags = {
    Name = "${var.domain_name}-site"
  }

  lifecycle {
    precondition {
      condition     = var.sse_algorithm != "aws:kms" || var.sse_kms_key_id != null
      error_message = "sse_kms_key_id must be provided when sse_algorithm == \"aws:kms\""
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  bucket = aws_s3_bucket.site.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.sse_algorithm
      kms_master_key_id = var.sse_algorithm == "aws:kms" ? var.sse_kms_key_id : null
    }
  }
}

resource "aws_s3_bucket_versioning" "site" {
  bucket = aws_s3_bucket.site.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket = aws_s3_bucket.site.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
