mock_provider "aws" {}
mock_provider "aws" {
  alias = "useast1"
}
mock_provider "cloudflare" {}

override_resource {
  target = aws_acm_certificate.cert
  values = {
    arn = "arn:aws:acm:us-east-1:123456789012:certificate/mock"
    domain_validation_options = [
      {
        domain_name           = "test.example.com"
        resource_record_name  = "_abcde.test.example.com."
        resource_record_type  = "CNAME"
        resource_record_value = "_validation.test.example.com."
      },
      {
        domain_name           = "example.com"
        resource_record_name  = "_root.example.com."
        resource_record_type  = "CNAME"
        resource_record_value = "_validation.example.com."
      }
    ]
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
    cloudflare_zone_id = "0123456789abcdef0123456789abcdef"
    log_retention_days = 1
  }

  assert {
    condition     = output.bucket_name != ""
    error_message = "bucket_name output must be non-empty"
  }

  assert {
    condition     = length(cloudflare_dns_record.acm_validation) == 2
    error_message = "expected two Cloudflare validation records (domain + apex)"
  }

  assert {
    condition     = cloudflare_dns_record.cdn_cname[0].content == aws_cloudfront_distribution.cdn.domain_name
    error_message = "Cloudflare CDN CNAME content should match the CloudFront distribution domain"
  }
}
