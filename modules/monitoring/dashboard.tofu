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

  dashboard_base = replace(var.domain_name, ".", "-")
  dashboard_name = format("%s-%s-visitors", local.dashboard_base, var.environment)
}

resource "aws_cloudwatch_dashboard" "site" {
  dashboard_name = local.dashboard_name
  dashboard_body = local.dashboard_body
}
