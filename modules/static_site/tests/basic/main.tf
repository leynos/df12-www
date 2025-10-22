terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = ">= 5.6.0"
    }
  }
}

module "static_site" {
  source = "../"

  domain_name        = "www.example.com"
  root_domain        = "example.com"
  log_retention_days = 30
  cloudflare_zone_id = "0123456789abcdef0123456789abcdef"

  providers = {
    aws         = aws
    aws.useast1 = aws.useast1
    cloudflare  = cloudflare
  }
}

provider "aws" {
  region = "us-west-2"
}

provider "aws" {
  alias  = "useast1"
  region = "us-east-1"
}

provider "cloudflare" {
  api_token = "dummy"
}
