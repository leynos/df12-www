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

