terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    godaddy-dns = {
      source  = "registry.terraform.io/veksh/godaddy-dns"
      version = ">= 0.3.12"
    }
  }
}

module "static_site" {
  source = "../"

  domain_name        = "www.example.com"
  root_domain        = "example.com"
  log_retention_days = 30

  providers = {
    aws         = aws
    aws.useast1 = aws.useast1
    godaddy-dns = godaddy-dns
  }
}

provider "aws" {
  region = "us-west-2"
}

provider "aws" {
  alias  = "useast1"
  region = "us-east-1"
}

provider "godaddy-dns" {}
