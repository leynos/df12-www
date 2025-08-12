resource "godaddy-dns_record" "acm_validation" {
  for_each = {
    for dvo in aws_acm_certificate.cert.domain_validation_options : dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  }

  domain = var.root_domain
  name   = replace(each.value.name, "${var.root_domain}.", "")
  type   = each.value.type
  data   = each.value.value
  ttl    = 600
}

resource "godaddy-dns_record" "cdn_cname" {
  domain = var.root_domain
  name   = replace(var.domain_name, ".${var.root_domain}", "")
  type   = "CNAME"
  data   = aws_cloudfront_distribution.cdn.domain_name
  ttl    = 600
}
