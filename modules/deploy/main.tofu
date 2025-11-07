locals {
  use_github_ssh         = trimspace(var.github_ssh_private_key) != ""
  github_repo_url        = local.use_github_ssh ? "git@github.com:${var.github_owner}/${var.github_repo}.git" : "https://github.com/${var.github_owner}/${var.github_repo}.git"
  github_token_basic_b64 = base64encode("x-access-token:${var.github_token}")
}

locals {
  git_clone_cmd_https = <<-EOC
    if [ -z "${var.github_token}" ]; then
      echo "github_token must be provided when github_ssh_private_key is empty" >&2
      exit 1
    fi
    cat >"$DIR/git.cfg" <<EOF
    [http]
        extraheader = AUTHORIZATION: Basic ${local.github_token_basic_b64}
    EOF
    export GIT_TERMINAL_PROMPT=0
    git -c include.path="$DIR/git.cfg" \
        clone --depth 1 --branch "${var.github_branch}" "${local.github_repo_url}" "$REPO_DIR" >/dev/null
  EOC

  git_clone_cmd_ssh = <<-EOC
    if [ -z "${var.github_ssh_private_key}" ]; then
      echo "github_ssh_private_key must be provided when github_token is empty" >&2
      exit 1
    fi
    command -v ssh >/dev/null 2>&1 || { echo "ssh not found on PATH" >&2; exit 1; }
    if [ -z "${var.github_known_hosts}" ]; then
      command -v ssh-keyscan >/dev/null 2>&1 || { echo "ssh-keyscan not found on PATH" >&2; exit 1; }
      ssh-keyscan github.com >"$DIR/known_hosts" 2>/dev/null
    else
      cat >"$DIR/known_hosts" <<'EOF'
${var.github_known_hosts}
EOF
    fi
    cat >"$DIR/github_key" <<'EOF'
${var.github_ssh_private_key}
EOF
    chmod 600 "$DIR/github_key"
    cat >"$DIR/ssh_config" <<'EOF'
    Host github.com
      HostName github.com
      IdentityFile "$DIR/github_key"
      StrictHostKeyChecking yes
      UserKnownHostsFile "$DIR/known_hosts"
    EOF
    export GIT_TERMINAL_PROMPT=0
    GIT_SSH_COMMAND="ssh -F \"$DIR/ssh_config\"" \
        git clone --depth 1 --branch "${var.github_branch}" "${local.github_repo_url}" "$REPO_DIR" >/dev/null
  EOC

  git_clone_cmd = local.use_github_ssh ? local.git_clone_cmd_ssh : local.git_clone_cmd_https
}

# Clone repo and sync content to S3 whenever commit changes
data "external" "git_sync" {
  program = ["bash", "-c", <<EOT
    set -euo pipefail
    command -v bash >/dev/null 2>&1 || { echo "bash not found on PATH" >&2; exit 1; }
    command -v git >/dev/null 2>&1 || { echo "git not found on PATH" >&2; exit 1; }
    DIR=$(mktemp -d)
    REPO_DIR="$DIR/repo"
    trap 'rm -rf "$DIR"' EXIT
    ${local.git_clone_cmd}
    cd "$REPO_DIR"
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
      command -v bash >/dev/null 2>&1 || { echo "bash not found on PATH" >&2; exit 1; }
      command -v bun >/dev/null 2>&1 || { echo "bun not found on PATH" >&2; exit 1; }
      echo "Syncing site to S3..."
      DIR=$(mktemp -d)
      REPO_DIR="$DIR/repo"
      trap 'rm -rf "$DIR"' EXIT
      ${local.git_clone_cmd}
      git -C "$REPO_DIR" checkout -q "${data.external.git_sync.result.commit}"
      echo "Installing dependencies..."
      bun install --cwd "$REPO_DIR" >/dev/null
      echo "Building static assets..."
      bun run --cwd "$REPO_DIR" build >/dev/null
      test -d "$REPO_DIR/${var.site_path}" || { echo "Site path '$REPO_DIR/${var.site_path}' not found" >&2; exit 1; }
      test -f "$REPO_DIR/${var.site_path}/index.html" || { echo "Expected index.html at '$REPO_DIR/${var.site_path}/index.html'" >&2; exit 1; }
      test -d "$REPO_DIR/${var.site_path}/assets" || { echo "Expected assets directory at '$REPO_DIR/${var.site_path}/assets'" >&2; exit 1; }
      test -d "$REPO_DIR/${var.site_path}/images" || { echo "Expected images directory at '$REPO_DIR/${var.site_path}/images'" >&2; exit 1; }
      aws s3 sync "$REPO_DIR/${var.site_path}/" "s3://${var.bucket_name}" --delete --exclude ".DS_Store"
      echo "Invalidating CloudFront cache..."
      aws cloudfront create-invalidation --distribution-id "${var.distribution_id}" --paths "/*"
    EOT
    working_dir = path.module
  }
}
