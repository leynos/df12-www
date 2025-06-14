###############################################################################
#  Static Site on S3 + CloudFront + GoDaddy DNS — Parameterised OpenTofu Stack
#
#  Features
#  --------
#  • Private S3 bucket (OAC‑only)
#  • CloudFront distribution with ACM TLS (us‑east‑1)
#  • GoDaddy DNS CNAME → CloudFront (and optional APEX redirect)
#  • GitHub -> S3 deployment (null_resource + local‑exec)
#  • Cost safeguards: AWS Budget + CloudWatch alarms + log lifecycle
#  • Lightweight CloudWatch dashboard for visits over time + geo locations
#
#  Notes
#  -----
#  • Requires OpenTofu ≥1.6 (Terraform syntax 1.6 compatible)
#  • Assumes you have AWS creds in the environment & GoDaddy API key/secret.
#  • "local-exec" provisioners run on *your* workstation; you need git & AWS CLI.
#  • For production CI/CD, replace the local-exec with a proper pipeline.
###############################################################################

########################################
# terraform {} block
########################################
terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    godaddy = {
      source  = "n3mk4/godaddy"
      version = "~> 1.4"
    }
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
    }
  }
}

########################################
# Providers
########################################
provider "aws" {
  region = var.aws_region
}

# ACM certs for CloudFront must live in us-east-1
provider "aws" {
  alias  = "useast1"
  region = "us-east-1"
}

provider "godaddy" {
  api_key    = var.godaddy_api_key
  api_secret = var.godaddy_api_secret
}

provider "github" {
  token = var.github_token
}

########################################
# Variables
########################################
variable "domain_name" {
  description = "The full domain for the site (e.g. www.example.com)"
  type        = string
}

variable "root_domain" {
  description = "The apex / root domain (e.g. example.com). Used for redirect records."
  type        = string
}

variable "aws_region" {
  description = "AWS region for the S3 bucket & CloudFront logs"
  type        = string
  default     = "eu-west-2" # London
}

variable "github_owner" {
  description = "GitHub organisation or user"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository containing the static site"
  type        = string
}

variable "github_branch" {
  description = "Branch to deploy"
  type        = string
  default     = "main"
}

variable "github_token" {
  description = "PAT with repo read access (required for private repos)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "budget_limit_gbp" {
  description = "Monthly cost limit that triggers email alerts (GBP)"
  type        = number
  default     = 5
}

variable "godaddy_api_key" {
  type        = string
  sensitive   = true
}

variable "godaddy_api_secret" {
  type        = string
  sensitive   = true
}

variable "log_retention_days" {
  description = "Days to retain CloudFront/S3 access logs"
  type        = number
  default     = 14
}

########################################
# Data sources
########################################
# Obtain latest commit SHA to trigger redeploys when content changes
# (works for public repos even without token)

data "github_repository" "site" {
  full_name = "${var.github_owner}/${var.github_repo}"
}

########################################
# S3 Buckets
########################################
# 1) Site bucket (private)
resource "aws_s3_bucket" "site" {
  bucket = var.domain_name
  force_destroy = true
  tags = {
    Name = "${var.domain_name}-site"
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

# 2) Logs bucket
resource "aws_s3_bucket" "logs" {
  bucket = "${var.domain_name}-logs"
  force_destroy = true
}

resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    id     = "expire-logs"
    status = "Enabled"

    expiration {
      days = var.log_retention_days
    }
  }
}

########################################
# S3 -> CloudFront Origin Access Control
########################################
resource "aws_cloudfront_origin_access_control" "oac" {
  name                              = "${var.domain_name}-oac"
  description                       = "OAC for ${var.domain_name}"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
  origin_access_control_origin_type = "s3"
}

########################################
# ACM Certificate (us-east-1)
########################################
resource "aws_acm_certificate" "cert" {
  provider          = aws.useast1
  domain_name       = var.domain_name
  validation_method = "DNS"
  subject_alternative_names = [var.root_domain]
}

# DNS validation records via GoDaddy
resource "godaddy_domain_record" "acm_validation" {
  for_each = {
    for dvo in aws_acm_certificate.cert.domain_validation_options : dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  }

  domain = var.root_domain
  name   = replace(each.value.name, "${var.root_domain}.", "")
  type   = each.value.type
  value  = each.value.value
  ttl    = 600
}

resource "aws_acm_certificate_validation" "cert_validation" {
  provider                = aws.useast1
  certificate_arn         = aws_acm_certificate.cert.arn
  validation_record_fqdns = [for r in godaddy_domain_record.acm_validation : r.fqdn]
}

########################################
# CloudFront Distribution
########################################
resource "aws_cloudfront_distribution" "cdn" {
  depends_on = [aws_acm_certificate_validation.cert_validation]

  enabled = true
  comment = var.domain_name

  origins {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = "s3-origin-${var.domain_name}"
    origin_access_control_id = aws_cloudfront_origin_access_control.oac.id
  }

  default_cache_behavior {
    target_origin_id       = "s3-origin-${var.domain_name}"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]

    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6" # CachingOptimized
  }

  price_class = "PriceClass_100"

  default_root_object = "index.html"

  logging_config {
    include_cookies = false
    bucket          = aws_s3_bucket.logs.bucket_domain_name
    prefix          = "cf/"
  }

  aliases = [var.domain_name]

  viewer_certificate {
    acm_certificate_arn            = aws_acm_certificate.cert.arn
    ssl_support_method             = "sni-only"
    minimum_protocol_version       = "TLSv1.2_2021"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  tags = {
    Name = "${var.domain_name}-cdn"
  }
}

########################################
# S3 Bucket Policy (allow CloudFront only)
########################################
resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowCloudFrontServicePrincipalReadOnly"
        Effect    = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = ["s3:GetObject"]
        Resource = ["${aws_s3_bucket.site.arn}/*"]
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.cdn.arn
          }
        }
      }
    ]
  })
}

########################################
# GoDaddy DNS Records
########################################
# CNAME www (or your subdomain) → CloudFront
resource "godaddy_domain_record" "cdn_cname" {
  domain = var.root_domain
  name   = replace(var.domain_name, ".${var.root_domain}", "")
  type   = "CNAME"
  value  = aws_cloudfront_distribution.cdn.domain_name
  ttl    = 600
}

# Optional: root domain redirect to www (GoDaddy HTTP redirect)
resource "godaddy_domain_record" "root_forward" {
  domain = var.root_domain
  name   = "@"
  type   = "FORWARD"
  value  = "https://${var.domain_name}"
  ttl    = 600
  provider_specific {
    include_path = true
    https        = true
    status_code  = 301
  }
}

########################################
# Deploy Site Content from GitHub → S3
########################################
# Clone repo & sync every plan/apply when commit hash changes

data "external" "git_sync" {
  program = ["bash", "-c", <<EOT
    set -e
    DIR=$(mktemp -d)
    trap 'rm -rf "$DIR"' EXIT
    git clone --depth 1 --branch ${var.github_branch} https://github.com/${var.github_owner}/${var.github_repo}.git "$DIR" >/dev/null 2>&1
    cd "$DIR"
    echo "{\"commit\":\"$(git rev-parse HEAD)\"}"
  EOT]
}

resource "null_resource" "deploy" {
  # Trigger when repo HEAD changes
  triggers = {
    commit = data.external.git_sync.result.commit
  }

  provisioner "local-exec" {
    command = <<EOT
      set -e
      echo "Syncing site to S3..."
      aws s3 sync $(pwd)/site s3://${aws_s3_bucket.site.id} --delete
      echo "Invalidating CloudFront cache..."
      aws cloudfront create-invalidation --distribution-id ${aws_cloudfront_distribution.cdn.id} --paths "/*"
    EOT
    working_dir = "${path.module}"
  }
}

########################################
# Cost Safeguards: AWS Budget + Alarms
########################################
resource "aws_budgets_budget" "monthly_limit" {
  name         = "static-site-budget"
  budget_type  = "COST"
  limit_amount = var.budget_limit_gbp
  limit_unit   = "GBP"
  time_unit    = "MONTHLY"

  cost_filters = {
    Service = ["AmazonS3", "Amazon CloudFront"]
  }

  notification {
    comparison_operator = "GREATER_THAN"
    threshold           = 50
    threshold_type      = "PERCENTAGE"
    notification_type   = "FORECASTED"
    subscriber_email_addresses = [var.budget_email]
  }

  notification {
    comparison_operator = "GREATER_THAN"
    threshold           = 100
    threshold_type      = "PERCENTAGE"
    notification_type   = "ACTUAL"
    subscriber_email_addresses = [var.budget_email]
  }
}

# CloudWatch Alarms on request spikes
resource "aws_cloudwatch_metric_alarm" "s3_requests_spike" {
  alarm_name          = "S3GetRequestsSpike"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  period              = 3600
  statistic           = "Sum"
  threshold           = 100000 # adjust to taste
  metric_name         = "GetRequests"
  namespace           = "AWS/S3"
  dimensions = {
    BucketName = aws_s3_bucket.site.bucket
    StorageType = "AllStorageTypes"
  }
  alarm_description = "Alert on unusual S3 GET request volume"
  treat_missing_data = "ignore"
}

resource "aws_cloudwatch_metric_alarm" "cf_requests_spike" {
  alarm_name          = "CFRequestsSpike"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  period              = 3600
  statistic           = "Sum"
  threshold           = 100000
  metric_name         = "Requests"
  namespace           = "AWS/CloudFront"
  dimensions = {
    DistributionId = aws_cloudfront_distribution.cdn.id
    Region         = "Global"
  }
  alarm_description = "Alert on unusual CloudFront request volume"
  treat_missing_data = "ignore"
}

########################################
# CloudWatch Dashboard: Visitors over Time + Geo
########################################
locals {
  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric",
        x    = 0,
        y    = 0,
        width  = 12,
        height = 6,
        properties = {
          metrics = [
            [ "AWS/CloudFront", "Requests", "DistributionId", aws_cloudfront_distribution.cdn.id, { "stat": "Sum", "region": "us-east-1", "label": "Requests" } ]
          ],
          period = 300,
          stat   = "Sum",
          title  = "Total Requests (5m)"
        }
      },
      {
        type = "metric",
        x    = 12,
        y    = 0,
        width  = 12,
        height = 6,
        properties = {
          metrics = [
            [ "AWS/CloudFront", "Requests", "DistributionId", aws_cloudfront_distribution.cdn.id, "Country", "US", { "stat": "Sum", "label": "US" } ],
            [ "...", "Country", "GB", { "stat": "Sum", "label": "GB" } ],
            [ "...", "Country", "DE", { "stat": "Sum", "label": "DE" } ]
          ],
          period = 3600,
          stat   = "Sum",
          view   = "timeSeries",
          title  = "Requests by Country (1h bins)"
        }
      }
    ]
  })
}

resource "aws_cloudwatch_dashboard" "site" {
  dashboard_name = "${var.domain_name}-visitors"
  dashboard_body = local.dashboard_body
}

########################################
# Outputs
########################################
output "cloudfront_domain" {
  value = aws_cloudfront_distribution.cdn.domain_name
}

output "site_url" {
  value = "https://${var.domain_name}"
}
