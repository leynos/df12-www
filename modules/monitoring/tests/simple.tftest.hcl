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
}
