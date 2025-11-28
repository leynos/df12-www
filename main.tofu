locals {
  use_scaleway = lower(trimspace(var.cloud_provider)) == "scaleway"
  use_aws      = !local.use_scaleway
}

module "site_aws" {
  count              = local.use_aws ? 1 : 0
  source             = "./modules/static_site"
  domain_name        = var.domain_name
  root_domain        = var.root_domain
  log_retention_days = var.log_retention_days
  cloudflare_zone_id = var.cloudflare_zone_id
  cloudflare_proxied = var.cloudflare_proxied
  sse_algorithm      = var.sse_algorithm
  sse_kms_key_id     = var.sse_kms_key_id
  force_destroy_site = var.force_destroy_site_bucket

  providers = {
    aws         = aws
    aws.useast1 = aws.useast1
    cloudflare  = cloudflare
  }
}

module "site_scaleway" {
  count              = local.use_scaleway ? 1 : 0
  source             = "./modules/static_site_scaleway"
  domain_name        = var.domain_name
  root_domain        = var.root_domain
  cloudflare_zone_id = var.cloudflare_zone_id
  cloudflare_proxied = var.cloudflare_proxied
  scaleway_region    = var.scaleway_region
  project_id         = var.scaleway_project_id

  providers = {
    scaleway   = scaleway
    cloudflare = cloudflare
  }
}

module "deploy_aws" {
  count                  = local.use_aws ? 1 : 0
  source                 = "./modules/deploy"
  bucket_name            = module.site_aws[0].bucket_name
  distribution_id        = module.site_aws[0].distribution_id
  github_owner           = var.github_owner
  github_repo            = var.github_repo
  github_branch          = var.github_branch
  github_token           = var.github_token
  github_ssh_private_key = var.github_ssh_private_key
  github_known_hosts     = var.github_known_hosts
  site_path              = var.site_path
}

module "deploy_scaleway" {
  count                  = local.use_scaleway ? 1 : 0
  source                 = "./modules/deploy_scaleway"
  bucket_name            = module.site_scaleway[0].bucket_name
  bucket_region          = var.scaleway_region
  github_owner           = var.github_owner
  github_repo            = var.github_repo
  github_branch          = var.github_branch
  github_token           = var.github_token
  github_ssh_private_key = var.github_ssh_private_key
  github_known_hosts     = var.github_known_hosts
  site_path              = var.site_path
  scaleway_access_key    = var.scaleway_access_key
  scaleway_secret_key    = var.scaleway_secret_key
  cloudflare_api_token   = var.cloudflare_api_token
  cloudflare_zone_id     = var.cloudflare_zone_id
}

module "monitoring_aws" {
  count            = local.use_aws ? 1 : 0
  source           = "./modules/monitoring"
  domain_name      = var.domain_name
  bucket_name      = module.site_aws[0].bucket_name
  distribution_id  = module.site_aws[0].distribution_id
  budget_limit_gbp = var.budget_limit_gbp
  budget_email     = var.budget_email
  environment      = var.environment
}

module "state_bucket" {
  count       = local.use_aws ? 1 : 0
  source      = "./modules/state_bucket"
  bucket_name = var.state_bucket_name

  providers = {
    aws = aws
  }
}
