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

  backend "local" {}
}
