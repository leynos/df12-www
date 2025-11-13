locals {
  provider_use_scaleway = lower(trimspace(var.cloud_provider)) == "scaleway"
  aws_provider_region   = local.provider_use_scaleway ? "us-east-1" : var.aws_region
}

provider "aws" {
  region                      = local.aws_provider_region
  access_key                  = local.provider_use_scaleway ? "not-used" : null
  secret_key                  = local.provider_use_scaleway ? "not-used" : null
  skip_credentials_validation = local.provider_use_scaleway
  skip_metadata_api_check     = local.provider_use_scaleway
  skip_requesting_account_id  = local.provider_use_scaleway

  default_tags {
    tags = {
      ManagedBy   = "OpenTofu"
      Environment = var.environment
      Project     = var.project_name
    }
  }
}

provider "aws" {
  alias                       = "useast1"
  region                      = "us-east-1"
  access_key                  = local.provider_use_scaleway ? "not-used" : null
  secret_key                  = local.provider_use_scaleway ? "not-used" : null
  skip_credentials_validation = local.provider_use_scaleway
  skip_metadata_api_check     = local.provider_use_scaleway
  skip_requesting_account_id  = local.provider_use_scaleway

  default_tags {
    tags = {
      ManagedBy   = "OpenTofu"
      Environment = var.environment
      Project     = var.project_name
    }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

provider "scaleway" {
  access_key      = var.scaleway_access_key
  secret_key      = var.scaleway_secret_key
  project_id      = var.scaleway_project_id
  organization_id = var.scaleway_organization_id
  region          = var.scaleway_region
  zone            = var.scaleway_zone
}
