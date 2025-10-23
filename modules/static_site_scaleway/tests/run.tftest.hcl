mock_provider "scaleway" {}
mock_provider "cloudflare" {}

run "plan" {
  command = plan

  variables {
    domain_name        = "www.example.com"
    root_domain        = "example.com"
    cloudflare_zone_id = "0123456789abcdef0123456789abcdef"
    cloudflare_proxied = false
    scaleway_region    = "fr-par"
    project_id         = "11111111-1111-1111-1111-111111111111"
  }

  assert {
    condition     = scaleway_object_bucket.site.name != ""
    error_message = "expected bucket to be defined"
  }

  assert {
    condition     = scaleway_object_bucket_website_configuration.site.bucket == scaleway_object_bucket.site.name
    error_message = "website configuration should target the bucket"
  }

  assert {
    condition     = cloudflare_dns_record.cdn_cname[0].content == "www.example.com.s3.fr-par.scw.cloud"
    error_message = "cdn CNAME should point at the Scaleway website endpoint"
  }
}
