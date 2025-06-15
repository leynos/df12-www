terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
  }
}

variable "domain_name" {
  type = string
}

variable "bucket_name" {
  type = string
}

variable "distribution_id" {
  type = string
}

variable "budget_limit_gbp" {
  type = number
}

variable "budget_email" {
  type = string
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

