locals {
  git_clone_cmd = <<-EOC
    cat >"$DIR/git.cfg" <<'EOF'
    [http]
        extraheader = AUTHORIZATION: bearer ${var.github_token}
    EOF
    git -c include.path="$DIR/git.cfg" \
        clone --depth 1 --branch ${var.github_branch} https://github.com/${var.github_owner}/${var.github_repo}.git "$DIR"
  EOC
}

# Clone repo and sync content to S3 whenever commit changes
data "external" "git_sync" {
  program = ["bash", "-c", <<EOT
    set -e
    command -v bash >/dev/null 2>&1 || { echo "bash not found on PATH" >&2; exit 1; }
    command -v git >/dev/null 2>&1 || { echo "git not found on PATH" >&2; exit 1; }
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
      git -C "$DIR" checkout -q "${data.external.git_sync.result.commit}"
      test -d "$DIR/${var.site_path}" || { echo "Site path '$DIR/${var.site_path}' not found" >&2; exit 1; }
      aws s3 sync "$DIR/${var.site_path}" s3://${var.bucket_name} --delete
      echo "Invalidating CloudFront cache..."
      aws cloudfront create-invalidation --distribution-id ${var.distribution_id} --paths "/*"
    EOT
    working_dir = path.module
  }
}

