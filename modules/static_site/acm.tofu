resource "aws_acm_certificate" "cert" {
  provider                  = aws.useast1
  domain_name               = local.domain_name_clean
  validation_method         = "DNS"
  subject_alternative_names = [local.root_domain_clean]

  lifecycle {
    create_before_destroy = true
    precondition {
      condition     = endswith(local.domain_name_clean, local.root_domain_clean)
      error_message = "domain_name must end with root_domain"
    }
  }
}

resource "aws_acm_certificate_validation" "cert_validation" {
  provider                = aws.useast1
  certificate_arn         = aws_acm_certificate.cert.arn
  validation_record_fqdns = [for r in cloudflare_dns_record.acm_validation : r.name]
}
