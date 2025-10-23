locals {
  git_clone_cmd = <<-EOC
    cat >"$DIR/git.cfg" <<'EOF'
    [http]
        extraheader = AUTHORIZATION: bearer ${var.github_token}
    EOF
    git -c include.path="$DIR/git.cfg" \
        clone --depth 1 --branch "${var.github_branch}" "https://github.com/${var.github_owner}/${var.github_repo}.git" "$DIR" >/dev/null
  EOC
}

data "external" "git_sync" {
  program = ["bash", "-c", <<EOT
    set -euo pipefail
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
      set -euo pipefail
      command -v aws >/dev/null 2>&1 || { echo "aws CLI not found on PATH" >&2; exit 1; }
      command -v git >/dev/null 2>&1 || { echo "git not found on PATH" >&2; exit 1; }
      command -v curl >/dev/null 2>&1 || { echo "curl not found on PATH" >&2; exit 1; }
      echo "Syncing site to Scaleway Object Storage..."
      DIR=$(mktemp -d)
      trap 'rm -rf "$DIR"' EXIT
      ${local.git_clone_cmd}
      git -C "$DIR" checkout -q "${data.external.git_sync.result.commit}"
      test -d "$DIR/${var.site_path}" || { echo "Site path '$DIR/${var.site_path}' not found" >&2; exit 1; }
      test -f "$DIR/${var.site_path}/index.html" || { echo "Expected index.html at '$DIR/${var.site_path}/index.html'" >&2; exit 1; }
      test -d "$DIR/${var.site_path}/assets" || { echo "Expected assets directory at '$DIR/${var.site_path}/assets'" >&2; exit 1; }
      test -d "$DIR/${var.site_path}/images" || { echo "Expected images directory at '$DIR/${var.site_path}/images'" >&2; exit 1; }
      aws --endpoint-url "$AWS_S3_ENDPOINT" s3 sync "$DIR/${var.site_path}/" "s3://${var.bucket_name}" --delete --exclude ".DS_Store"
      echo "Purging Cloudflare cache..."
      curl -s -X POST "https://api.cloudflare.com/client/v4/zones/${var.cloudflare_zone_id}/purge_cache" \
        -H "Authorization: Bearer $CF_API_TOKEN" \
        -H "Content-Type: application/json" \
        --data '{"purge_everything":true}' >/dev/null
      echo "Deployment complete."
    EOT
    working_dir = path.module
    environment = {
      AWS_ACCESS_KEY_ID     = var.scaleway_access_key
      AWS_SECRET_ACCESS_KEY = var.scaleway_secret_key
      AWS_DEFAULT_REGION    = var.bucket_region
      AWS_S3_ENDPOINT       = "https://s3.${var.bucket_region}.scw.cloud"
      CF_API_TOKEN          = var.cloudflare_api_token
    }
  }
}
