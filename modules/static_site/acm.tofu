resource "aws_acm_certificate" "cert" {
  provider                  = aws.useast1
  domain_name               = var.domain_name
  validation_method         = "DNS"
  subject_alternative_names = [var.root_domain]
}

resource "aws_acm_certificate_validation" "cert_validation" {
  provider                = aws.useast1
  certificate_arn         = aws_acm_certificate.cert.arn
  validation_record_fqdns = [for r in godaddy-dns_record.acm_validation : r.fqdn]
}
