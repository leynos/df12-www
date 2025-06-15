terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
  }
}

variable "domain_name" {
  description = "Fully qualified domain name for monitoring dashboard"
  type        = string
  nullable    = false

  validation {
    condition     = length(var.domain_name) > 0 && can(regex("^([a-zA-Z0-9-]+\\.)+[a-zA-Z]{2,}$", var.domain_name))
    error_message = "Domain name must be a valid non-empty hostname"
  }
}

variable "bucket_name" {
  description = "Name of the S3 bucket storing site content"
  type        = string
  nullable    = false
}

variable "distribution_id" {
  description = "ID of the CloudFront distribution"
  type        = string
  nullable    = false
}

variable "budget_limit_gbp" {
  description = "Monthly cost limit that triggers alerts, in GBP"
  type        = number
  nullable    = false
}

variable "budget_email" {
  description = "Email address for budget notifications"
  type        = string
  nullable    = false
}

resource "aws_budgets_budget" "monthly_limit" {
  name         = "static-site-budget"
  budget_type  = "COST"
  limit_amount = var.budget_limit_gbp
  limit_unit   = "GBP"
  time_unit    = "MONTHLY"
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 50
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_email]
  }
}

resource "aws_cloudwatch_metric_alarm" "s3_requests_spike" {
  alarm_name          = "S3GetRequestsSpike"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  period              = 3600
  statistic           = "Sum"
  threshold           = 100000
  metric_name         = "GetRequests"
  namespace           = "AWS/S3"
  dimensions = {
    BucketName  = var.bucket_name
    StorageType = "AllStorageTypes"
  }
  alarm_description  = "Alert on unusual S3 GET request volume"
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
    DistributionId = var.distribution_id
    Region         = "Global"
  }
  alarm_description  = "Alert on unusual CloudFront request volume"
  treat_missing_data = "ignore"
}

locals {
  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/CloudFront", "Requests", "DistributionId", var.distribution_id, { "stat" : "Sum", "region" : "us-east-1", "label" : "Requests" }]
          ]
          period = 300
          stat   = "Sum"
          title  = "Total Requests (5m)"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          metrics = [
            ["AWS/CloudFront", "Requests", "DistributionId", var.distribution_id, "Country", "US", { "stat" : "Sum", "label" : "US" }],
            ["...", "Country", "GB", { "stat" : "Sum", "label" : "GB" }],
            ["...", "Country", "DE", { "stat" : "Sum", "label" : "DE" }]
          ]
          period = 3600
          stat   = "Sum"
          view   = "timeSeries"
          title  = "Requests by Country (1h bins)"
        }
      }
    ]
  })
}

resource "aws_cloudwatch_dashboard" "site" {
  dashboard_name = "${replace(var.domain_name, ".", "-")}-visitors"
  dashboard_body = local.dashboard_body
}

