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
    domain_name      = "test.example.com"
    bucket_name      = "test-bucket"
    distribution_id  = "TEST123"
    budget_limit_gbp = 20
    budget_email     = "alerts@example.com"
  }
  assert {
    condition     = testing.plan.resource_changes["aws_budgets_budget.monthly_limit"].change.after.limit_amount == 20
    error_message = "Budget limit should be 20"
  }
}
