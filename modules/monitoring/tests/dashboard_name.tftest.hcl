terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
  }
}

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
    condition     = testing.plan.resource_changes["aws_cloudwatch_dashboard.site"].change.after.dashboard_name == "demo.example.com-visitors"
    error_message = "Dashboard name mismatch"
  }
}
