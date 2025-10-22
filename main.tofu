module "site" {
  source             = "./modules/static_site"
  domain_name        = var.domain_name
  root_domain        = var.root_domain
  log_retention_days = var.log_retention_days
  cloudflare_zone_id = var.cloudflare_zone_id
  cloudflare_proxied = var.cloudflare_proxied

  providers = {
    aws         = aws
    aws.useast1 = aws.useast1
    cloudflare  = cloudflare
  }
}

module "deploy" {
  source          = "./modules/deploy"
  bucket_name     = module.site.bucket_name
  distribution_id = module.site.distribution_id
  github_owner    = var.github_owner
  github_repo     = var.github_repo
  github_branch   = var.github_branch
  github_token    = var.github_token
  site_path       = var.site_path
}

module "monitoring" {
  source           = "./modules/monitoring"
  domain_name      = var.domain_name
  bucket_name      = module.site.bucket_name
  distribution_id  = module.site.distribution_id
  budget_limit_gbp = var.budget_limit_gbp
  budget_email     = var.budget_email
  environment      = var.environment
}
