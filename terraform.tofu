terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    scaleway = {
      source  = "scaleway/scaleway"
      version = "~> 2.28.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.6.0"
    }
  }

  backend "s3" {
    bucket = "df12-www-state"
    key    = "envs/prod/terraform.tfstate"

    region = "fr-par"
    endpoints = {
      s3 = "https://s3.fr-par.scw.cloud"
    }

    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_credentials_validation = true
    use_path_style              = true
    use_lockfile                = true
    encrypt                     = true
  }
}
