mock_provider "aws" {}

run "budget_notifications" {
  command = plan

  variables {
    domain_name      = "example.com"
    bucket_name      = "logs"
    distribution_id  = "DIST123"
    budget_limit_gbp = 20
    budget_email     = "ops@example.com"
  }

  assert {
    condition     = tonumber(aws_budgets_budget.monthly_limit.limit_amount) == 20
    error_message = "Budget limit should be 20 GBP"
  }

  assert {
    condition     = contains(flatten(aws_budgets_budget.monthly_limit.notification[*].subscriber_email_addresses), "ops@example.com")
    error_message = "Subscriber email not set correctly"
  }
}

run "alarms_use_inputs" {
  command = plan

  variables {
    domain_name      = "example.com"
    bucket_name      = "my-bucket"
    distribution_id  = "ABC123"
    budget_limit_gbp = 10
    budget_email     = "ops@example.com"
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.s3_requests_spike.dimensions.BucketName == "my-bucket"
    error_message = "S3 alarm should use provided bucket name"
  }

  assert {
    condition     = aws_cloudwatch_metric_alarm.cf_requests_spike.dimensions.DistributionId == "ABC123"
    error_message = "CloudFront alarm should use provided distribution id"
  }
}

run "dashboard_metric" {
  command = plan

  variables {
    domain_name      = "monitor.example.com"
    bucket_name      = "dummy"
    distribution_id  = "XYZ987"
    budget_limit_gbp = 1
    budget_email     = "ops@example.com"
  }

  assert {
    condition     = aws_cloudwatch_dashboard.site.dashboard_name == "monitor-example-com-visitors"
    error_message = "Dashboard name incorrect"
  }

  assert {
    condition     = strcontains(aws_cloudwatch_dashboard.site.dashboard_body, "XYZ987")
    error_message = "Dashboard body should reference distribution id"
  }
}

run "dashboard_multi_domain" {
  command = plan

  variables {
    domain_name      = "a.b.example.com"
    bucket_name      = "dummy"
    distribution_id  = "XYZ987"
    budget_limit_gbp = 1
    budget_email     = "ops@example.com"
  }

  assert {
    condition     = aws_cloudwatch_dashboard.site.dashboard_name == "a-b-example-com-visitors"
    error_message = "Multi-level dashboard name incorrect"
  }
}
