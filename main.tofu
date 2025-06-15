provider "aws" {
  region = var.aws_region
}

provider "aws" {
  alias  = "useast1"
  region = "us-east-1"
}

provider "godaddy-dns" {
  api_key    = var.godaddy_api_key
  api_secret = var.godaddy_api_secret
}

provider "github" {
  token = var.github_token
}

module "site" {
  source             = "./modules/static_site"
  domain_name        = var.domain_name
  root_domain        = var.root_domain
  log_retention_days = var.log_retention_days

  providers = {
    aws         = aws
    aws.useast1 = aws.useast1
    godaddy-dns = godaddy-dns
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
}
