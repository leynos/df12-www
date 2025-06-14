run "plan" {
  command = plan
  module {
    source = "../"
  }
  variables {
    domain_name      = "demo.example.com"
    bucket_name      = "demo-bucket"
    distribution_id  = "DEMO123"
    budget_limit_gbp = 5
    budget_email     = "alerts@example.com"
  }
  assert {
    condition     = aws_cloudwatch_dashboard.site.dashboard_name == "demo.example.com-visitors"
    error_message = "Dashboard name mismatch"
  }
}
