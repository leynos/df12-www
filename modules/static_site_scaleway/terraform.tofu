terraform {
  required_version = ">= 1.6.0"
  required_providers {
    scaleway = {
      source  = "scaleway/scaleway"
      version = "~> 2.28.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.6.0"
    }
  }
}
