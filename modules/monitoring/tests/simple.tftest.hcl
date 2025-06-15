terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
  }
}

run "default" {
  command = plan
  module {
    source = "../"
  }
  variables {
    domain_name      = "foo"
    bucket_name      = "bar"
    distribution_id  = "baz"
    budget_limit_gbp = 10
    budget_email     = "e@example.com"
  }
  assert {
    condition     = testing.plan.resource_changes["aws_budgets_budget.monthly_limit"].change.after.time_unit == "MONTHLY"
    error_message = "Budget time unit should be monthly"
  }
}
