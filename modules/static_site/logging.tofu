locals {
  logs_bucket_name = "${replace(lower(replace(trimsuffix(local.domain_name_clean, "."), "*.", "")), "_", "-")}-logs"
  logs_kms_key_arn = var.sse_kms_key_id != null ? var.sse_kms_key_id : (var.sse_algorithm == "aws:kms" ? aws_kms_key.logs[0].arn : null)
}

data "aws_caller_identity" "current" {}

resource "aws_kms_key" "logs" {
  count       = var.sse_algorithm == "aws:kms" && var.sse_kms_key_id == null ? 1 : 0
  description = "KMS key for S3 log encryption"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowRoot"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowLogDelivery"
        Effect = "Allow"
        Principal = {
          Service = "delivery.logs.amazonaws.com"
        }
        Action   = ["kms:Encrypt", "kms:GenerateDataKey*"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_s3_bucket" "logs" {
  bucket        = local.logs_bucket_name
  force_destroy = var.force_destroy_logs

  lifecycle {
    precondition {
      condition     = var.sse_algorithm != "aws:kms" || local.logs_kms_key_arn != null
      error_message = "Provide sse_kms_key_id or allow module to create a key when sse_algorithm == \"aws:kms\""
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.sse_algorithm
      kms_master_key_id = var.sse_algorithm == "aws:kms" ? local.logs_kms_key_arn : null
    }
  }
}

resource "aws_s3_bucket_ownership_controls" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_public_access_block" "logs" {
  bucket                  = aws_s3_bucket.logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    id     = "expire-logs"
    status = "Enabled"

    filter {
      prefix = ""
    }

    expiration {
      days = var.log_retention_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

resource "aws_s3_bucket_policy" "logs" {
  bucket = aws_s3_bucket.logs.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowLogDelivery"
        Effect = "Allow"
        Principal = {
          Service = "delivery.logs.amazonaws.com"
        }
        Action   = ["s3:PutObject", "s3:PutObjectAcl"]
        Resource = "${aws_s3_bucket.logs.arn}/*"
        Condition = {
          StringEquals = {
            "s3:x-amz-acl" = "bucket-owner-full-control"
          }
        }
      }
    ]
  })
}

# If supplying an external KMS key via sse_kms_key_id, ensure its policy allows delivery.logs.amazonaws.com to encrypt objects.
