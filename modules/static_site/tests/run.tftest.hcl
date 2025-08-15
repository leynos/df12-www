mock_provider "aws" {}
mock_provider "aws" {
  alias = "useast1"
}
mock_provider "godaddy-dns" {}

override_resource {
  target = aws_acm_certificate.cert
  values = {
    arn = "arn:aws:acm:us-east-1:123456789012:certificate/mock"
  }
}

override_data {
  target = data.aws_caller_identity.current
  values = {
    account_id = "123456789012"
  }
}

run "plan" {
  command = plan

  variables {
    domain_name        = "test.example.com"
    root_domain        = "example.com"
    log_retention_days = 1
  }

  assert {
    condition     = length(tostring(module.static_site.bucket_name)) > 0
    error_message = "bucket_name output must be non-empty"
  }
}
