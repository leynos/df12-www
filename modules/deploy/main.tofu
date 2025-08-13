locals {
  git_clone_cmd = "git clone --depth 1 --branch ${var.github_branch} https://github.com/${var.github_owner}/${var.github_repo}.git \"$DIR\" >/dev/null 2>&1"
}

# Clone repo and sync content to S3 whenever commit changes
data "external" "git_sync" {
  program = ["bash", "-c", <<EOT
    set -e
    DIR=$(mktemp -d)
    trap 'rm -rf "$DIR"' EXIT
    ${local.git_clone_cmd}
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
      command -v aws >/dev/null 2>&1 || { echo "aws CLI not found on PATH" >&2; exit 1; }
      command -v git >/dev/null 2>&1 || { echo "git not found on PATH" >&2; exit 1; }
      command -v bash >/dev/null 2>&1 || { echo "bash not found on PATH" >&2; exit 1; }
      echo "Syncing site to S3..."
      DIR=$(mktemp -d)
      trap 'rm -rf "$DIR"' EXIT
      ${local.git_clone_cmd}
      aws s3 sync "$DIR/${var.site_path}" s3://${var.bucket_name} --delete
      echo "Invalidating CloudFront cache..."
      aws cloudfront create-invalidation --distribution-id ${var.distribution_id} --paths "/*"
    EOT
    working_dir = path.module
  }
}

