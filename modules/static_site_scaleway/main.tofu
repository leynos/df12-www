locals {
  bucket_name   = replace(lower(var.domain_name), "_", "-")
  subdomain     = trimsuffix(var.domain_name, ".${var.root_domain}")
  bucket_domain = "${local.bucket_name}.s3.${var.scaleway_region}.scw.cloud"
}

resource "scaleway_object_bucket" "site" {
  name       = local.bucket_name
  project_id = var.project_id
  region     = var.scaleway_region

  versioning {
    enabled = true
  }
}

resource "scaleway_object_bucket_acl" "site" {
  bucket = scaleway_object_bucket.site.name
  region = var.scaleway_region
  acl    = "public-read"
}

resource "scaleway_object_bucket_website_configuration" "site" {
  bucket = scaleway_object_bucket.site.name
  region = var.scaleway_region

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "index.html"
  }
}

resource "cloudflare_dns_record" "cdn_cname" {
  count   = local.subdomain == "" ? 0 : 1
  zone_id = var.cloudflare_zone_id
  name    = local.subdomain
  type    = "CNAME"
  content = local.bucket_domain
  ttl     = var.cloudflare_proxied ? 1 : 600
  proxied = var.cloudflare_proxied
}

resource "cloudflare_dns_record" "root_cname" {
  count   = local.subdomain == "" ? 1 : 0
  zone_id = var.cloudflare_zone_id
  name    = "@"
  type    = "CNAME"
  content = local.bucket_domain
  ttl     = var.cloudflare_proxied ? 1 : 600
  proxied = var.cloudflare_proxied
}
