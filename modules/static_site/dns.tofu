locals {
  subdomain = trimsuffix(local.domain_name_clean, ".${local.root_domain_clean}")
}

resource "cloudflare_dns_record" "acm_validation" {
  for_each = {
    for dvo in aws_acm_certificate.cert.domain_validation_options : dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  }

  zone_id = local.cloudflare_zone_id_clean
  name    = trimsuffix(each.value.name, ".")
  type    = each.value.type
  content = trimsuffix(each.value.value, ".")
  ttl     = 600
  proxied = false

  lifecycle {
    precondition {
      condition     = endswith(local.domain_name_clean, local.root_domain_clean)
      error_message = "domain_name must end with root_domain"
    }
  }
}

resource "cloudflare_dns_record" "cdn_cname" {
  count   = local.subdomain == "" ? 0 : 1
  zone_id = local.cloudflare_zone_id_clean
  name    = local.subdomain
  type    = "CNAME"
  content = aws_cloudfront_distribution.cdn.domain_name
  ttl     = var.cloudflare_proxied ? 1 : 600
  proxied = var.cloudflare_proxied

  lifecycle {
    precondition {
      condition     = endswith(local.domain_name_clean, local.root_domain_clean)
      error_message = "domain_name must end with root_domain"
    }
  }
}
