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
    cat >"$DIR/ssh_config" <<EOF
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
      command -v curl >/dev/null 2>&1 || { echo "curl not found on PATH" >&2; exit 1; }
      command -v bun >/dev/null 2>&1 || { echo "bun not found on PATH" >&2; exit 1; }
      echo "Syncing site to Scaleway Object Storage..."
      DIR=$(mktemp -d)
      REPO_DIR="$DIR/repo"
      trap 'rm -rf "$DIR"' EXIT
      ${local.git_clone_cmd}
      git -C "$REPO_DIR" checkout -q "${data.external.git_sync.result.commit}"
      echo "Installing dependencies..."
      bun install --cwd "$REPO_DIR"
      echo "Building static assets..."
      bun run --cwd "$REPO_DIR" build
      test -d "$REPO_DIR/${var.site_path}" || { echo "Site path '$REPO_DIR/${var.site_path}' not found" >&2; exit 1; }
      test -f "$REPO_DIR/${var.site_path}/index.html" || { echo "Expected index.html at '$REPO_DIR/${var.site_path}/index.html'" >&2; exit 1; }
      test -d "$REPO_DIR/${var.site_path}/assets" || { echo "Expected assets directory at '$REPO_DIR/${var.site_path}/assets'" >&2; exit 1; }
      test -d "$REPO_DIR/${var.site_path}/images" || { echo "Expected images directory at '$REPO_DIR/${var.site_path}/images'" >&2; exit 1; }
      if ! env | grep -q '^MIN_SITE_FILES='; then
        MIN_SITE_FILES=10
      fi
      FILE_COUNT="$(find "$REPO_DIR/${var.site_path}" -type f ! -name '.DS_Store' ! -name '.*' 2>/dev/null | wc -l || echo 0)"
      if [ "$FILE_COUNT" -lt "$MIN_SITE_FILES" ]; then
        echo "Refusing to sync: only $FILE_COUNT files under '$REPO_DIR/${var.site_path}' (minimum $MIN_SITE_FILES required)" >&2
        exit 1
      fi
      S3_DELETE_FLAG="--delete"
      if env | grep -q '^DRY_RUN='; then
        if [ "$DRY_RUN" != "0" ]; then
          echo "DRY_RUN enabled; running S3 sync without --delete"
          S3_DELETE_FLAG=""
        fi
      fi
      echo "Syncing versioned static assets with long-lived cache headers..."
      if [ -n "$S3_DELETE_FLAG" ]; then
        aws --endpoint-url "$AWS_S3_ENDPOINT" s3 sync "$REPO_DIR/${var.site_path}/" "s3://${var.bucket_name}" \
          --delete \
          --exclude ".DS_Store" \
          --exclude "*.html" \
          --cache-control "public, max-age=31536000, immutable" \
          --acl public-read
      else
        aws --endpoint-url "$AWS_S3_ENDPOINT" s3 sync "$REPO_DIR/${var.site_path}/" "s3://${var.bucket_name}" \
          --exclude ".DS_Store" \
          --exclude "*.html" \
          --cache-control "public, max-age=31536000, immutable" \
          --acl public-read
      fi
      echo "Syncing HTML documents with short-lived cache headers..."
      if [ -n "$S3_DELETE_FLAG" ]; then
        aws --endpoint-url "$AWS_S3_ENDPOINT" s3 sync "$REPO_DIR/${var.site_path}/" "s3://${var.bucket_name}" \
          --delete \
          --exclude ".DS_Store" \
          --exclude "*" \
          --include "index.html" \
          --include "*.html" \
          --cache-control "public, max-age=0, must-revalidate" \
          --acl public-read
      else
        aws --endpoint-url "$AWS_S3_ENDPOINT" s3 sync "$REPO_DIR/${var.site_path}/" "s3://${var.bucket_name}" \
          --exclude ".DS_Store" \
          --exclude "*" \
          --include "index.html" \
          --include "*.html" \
          --cache-control "public, max-age=0, must-revalidate" \
          --acl public-read
      fi
      echo "Purging Cloudflare cache..."
      CF_RESP_FILE="$DIR/cf_purge_response.json"
      CF_HEADER_FILE="$DIR/cf_purge_headers.txt"
      curl -sS -o "$CF_RESP_FILE" -D "$CF_HEADER_FILE" \
        -X POST "https://api.cloudflare.com/client/v4/zones/${var.cloudflare_zone_id}/purge_cache" \
        -H "Authorization: Bearer $CF_API_TOKEN" \
        -H "Content-Type: application/json" \
        --data '{"purge_everything":true}'
      CF_STATUS="$(awk 'NR==1 {print $2}' "$CF_HEADER_FILE")"
      command -v python3 >/dev/null 2>&1 || { echo "python3 not found; cannot validate Cloudflare response" >&2; exit 1; }
      python3 - "$CF_RESP_FILE" "$CF_STATUS" <<'PY'
import json
import sys
from typing import Any

response_path, status_text = sys.argv[1], sys.argv[2]

try:
    status_code = int(status_text)
except ValueError:
    print(f"Invalid HTTP status from curl: {status_text!r}", file=sys.stderr)
    sys.exit(1)

try:
    with open(response_path, encoding="utf-8") as handle:
        payload: dict[str, Any] = json.load(handle)
except Exception as exc:  # pragma: no cover - diagnostic path
    print(f"Failed to parse Cloudflare response JSON: {exc!r}", file=sys.stderr)
    sys.exit(1)

success = payload.get("success")
errors = payload.get("errors") or []

if status_code != 200 or not success or errors:
    print(
        f"Cloudflare purge failed with status {status_code}: {payload!r}",
        file=sys.stderr,
    )
    sys.exit(1)
PY
      echo "Cloudflare cache purge succeeded."
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
