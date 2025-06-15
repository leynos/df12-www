terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
    external = {
      source = "hashicorp/external"
    }
    null = {
      source = "hashicorp/null"
    }
  }
}

variable "bucket_name" {
  description = "Name of the S3 bucket hosting the site"
  type        = string
  nullable    = false
}

variable "distribution_id" {
  description = "ID of the CloudFront distribution"
  type        = string
  nullable    = false
}

variable "github_owner" {
  description = "GitHub organization or user that owns the repository"
  type        = string
  nullable    = false
}

variable "github_repo" {
  description = "Name of the repository to deploy"
  type        = string
  nullable    = false
}

variable "github_branch" {
  description = "Branch containing site content"
  type        = string
  nullable    = false
}

variable "github_token" {
  description = "Personal access token for GitHub API"
  type        = string
  nullable    = false
}

variable "site_path" {
  type    = string
  default = "site"
}

# Clone repo and sync content to S3 whenever commit changes
data "external" "git_sync" {
  program = ["bash", "-c", <<EOT
    set -e
    DIR=$(mktemp -d)
    trap 'rm -rf "$DIR"' EXIT
    git clone --depth 1 --branch ${var.github_branch} https://github.com/${var.github_owner}/${var.github_repo}.git "$DIR" >/dev/null 2>&1
    cd "$DIR"
    echo "{\"commit\":\"$(git rev-parse HEAD)\"}"
  EOT
  ]
}

resource "null_resource" "deploy" {
  triggers = {
    commit = data.external.git_sync.result.commit
  }

  provisioner "local-exec" {
    command     = <<EOT
      set -e
      echo "Syncing site to S3..."
      aws s3 sync "${path.module}/${var.site_path}" s3://${var.bucket_name} --delete
      echo "Invalidating CloudFront cache..."
      aws cloudfront create-invalidation --distribution-id ${var.distribution_id} --paths "/*"
    EOT
    working_dir = path.module
  }
}

