provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      ManagedBy   = "terraform"
      Environment = var.environment
      Project     = var.project_name
    }
  }
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
