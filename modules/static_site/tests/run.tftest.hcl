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

run "plan" {
  command = plan

  variables {
    domain_name        = "test.example.com"
    root_domain        = "example.com"
    log_retention_days = 1
  }
}
