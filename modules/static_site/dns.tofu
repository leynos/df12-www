locals {
  subdomain = trimsuffix(trimsuffix(var.domain_name, ".${var.root_domain}."), ".${var.root_domain}")
}

resource "cloudflare_dns_record" "acm_validation" {
  for_each = {
    for dvo in aws_acm_certificate.cert.domain_validation_options : dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  }

  zone_id = var.cloudflare_zone_id
  name    = trimsuffix(each.value.name, ".")
  type    = each.value.type
  content = trimsuffix(each.value.value, ".")
  ttl     = 600
  proxied = false

  lifecycle {
    precondition {
      condition     = endswith(var.domain_name, var.root_domain)
      error_message = "domain_name must end with root_domain"
    }
  }
}

resource "cloudflare_dns_record" "cdn_cname" {
  count   = local.subdomain == "" ? 0 : 1
  zone_id = var.cloudflare_zone_id
  name    = local.subdomain
  type    = "CNAME"
  content = aws_cloudfront_distribution.cdn.domain_name
  ttl     = var.cloudflare_proxied ? 1 : 600
  proxied = var.cloudflare_proxied

  lifecycle {
    precondition {
      condition     = endswith(var.domain_name, var.root_domain)
      error_message = "domain_name must end with root_domain"
    }
  }
}
