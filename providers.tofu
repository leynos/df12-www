provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      ManagedBy   = "OpenTofu"
      Environment = var.environment
      Project     = var.project_name
    }
  }
}

provider "aws" {
  alias  = "useast1"
  region = "us-east-1"
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

provider "github" {
  token = var.github_token
}
