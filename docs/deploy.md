# Deployment Guide — df12 Static Site

_Updated: 26 October 2025_

This guide explains how to configure, build, and deploy the df12 static site
using the OpenTofu infrastructure stack. It consolidates all deployment
guidance for this repository, covering prerequisites, environment setup,
automation, and rollback strategies.

## 1. Prerequisites

- **Tooling**
  - [Bun](https://bun.sh) ≥ 1.1 for building the Tailwind bundle (the deploy modules now run `bun install`/`bun run build` during `apply`, so Bun must exist on the host executing OpenTofu).
  - [OpenTofu CLI](https://opentofu.org) ≥ 1.6.0.
  - AWS CLI (required: used both for AWS deploys *and* for Scaleway uploads via the S3-compatible endpoint).
  - Optional: Scaleway CLI (`scw`) for ad-hoc diagnostics when targeting Scaleway.
- **Accounts & credentials**
  - AWS account with permissions to manage S3, CloudFront, ACM, IAM, and Budgets
    (required when `cloud_provider = "aws"`).
  - Scaleway project with Object Storage and Cockpit access rights (required
    when `cloud_provider = "scaleway"`). Create API access/secret keys with
    project-level scope.
  - Cloudflare account with access to the DNS zone that will host the site.
  - GitHub repository containing the site source (this repo) and a personal
    access token (PAT) for cloning. The deployment module uses a temporary Git
    config include to inject the PAT as an HTTP Authorization header so the
    token never appears in process arguments.
- **Local environment**
  - Clone the repo: `git clone git@github.com:leynos/df12-www.git`.
  - Install dependencies: `bun install`.

## 2. Configuration Inputs

All inputs now live in a single TOML file (default
`~/.config/df12-www/config.toml`). The CLI reads this file, merges any CLI or
environment overrides, then generates temporary `tfbackend` and `tfvars` files
for OpenTofu. No checked-in `.tfvars` or `.tfbackend` files are needed.

### `[site]` variables (forwarded to `tfvars`)

| Variable                                       | Purpose                                                                                   |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `domain_name`                                  | Fully qualified domain that will serve the site (e.g. `www.example.com`).                 |
| `root_domain`                                  | Apex domain used for DNS validation (e.g. `example.com`). Must match the Cloudflare zone. |
| `aws_region`                                   | Region for S3 buckets and logging (defaults to `eu-west-2`).                              |
| `environment`                                  | Environment label used in tagging (e.g. `dev`, `prod`).                                   |
| `project_name`                                 | Tag prefix for identifying resources (defaults to `df12-www`).                            |
| `github_owner`, `github_repo`, `github_branch` | Repository information for fetching the built site.                                       |
| `github_token`                                 | PAT with `repo` scope for authenticated HTTPS clones (set to empty when using SSH).       |
| `github_ssh_private_key`                       | Optional PEM-formatted private key for `git@github.com` clones when no PAT is supplied.   |
| `github_known_hosts`                           | Optional newline-delimited `known_hosts` entries; defaults to `ssh-keyscan github.com`.   |
| `site_path`                                    | Relative path to the built static site (defaults to `public`).                            |
| `force_destroy_site_bucket`                    | Controls whether the primary site bucket can be force-destroyed (defaults to `true`).     |
| `cloudflare_api_token`                         | API token with DNS edit permissions for the zone.                                         |
| `cloudflare_zone_id`                           | 32-character Cloudflare zone identifier for `root_domain`.                                |
| `cloudflare_proxied`                           | Set to `true` to enable Cloudflare proxying for the CDN CNAME.                            |
| `cloud_provider`                               | Either `aws` or `scaleway` (defaults to `aws`).                                           |
| `budget_limit_gbp`                             | Monthly AWS budget threshold in GBP for cost alerts.                                      |
| `budget_email`                                 | Email address that receives AWS/Scaleway alert notifications.                             |
| `log_retention_days`                           | CloudFront log retention (defaults to 14 days, ignored on Scaleway).                      |

Additional variables for `cloud_provider = "scaleway"`:

| Variable                    | Purpose                                                             |
| --------------------------- | ------------------------------------------------------------------- |
| `scaleway_access_key`       | API access key with permissions for Object Storage and Cockpit.     |
| `scaleway_secret_key`       | Secret key paired with the access key.                              |
| `scaleway_project_id`       | Project UUID that owns the static assets.                           |
| `scaleway_organization_id`  | Optional organization UUID (leave empty for project-scoped access). |
| `scaleway_region`           | Object Storage region (e.g. `fr-par`).                              |
| `scaleway_zone`             | Service zone (e.g. `fr-par-1`).                                     |

### `[backend]` variables (backend state bucket)

| Variable   | Purpose                                                     |
| ---------- | ----------------------------------------------------------- |
| `bucket`   | Name of the S3-compatible bucket used for OpenTofu state.   |
| `region`   | Region for the backend bucket (e.g. `fr-par`).              |
| `endpoint` | Optional custom endpoint for S3-compatible backends.        |
| `encrypt`  | Set `false` to disable SSE for providers that reject it.    |

### `[auth]` variables (persisted credentials)

| Variable                 | Purpose                                                            |
| ------------------------ | ------------------------------------------------------------------ |
| `aws_access_key_id`      | AWS-style access key used for backend auth (works with Scaleway).  |
| `aws_secret_access_key`  | Secret key paired with the access key.                             |
| `scw_access_key`         | Optional override for provider auth; falls back to AWS key.        |
| `scw_secret_key`         | Optional override for provider auth; falls back to AWS secret.     |
| `cloudflare_api_token`   | Forwarded to both env vars and `TF_VAR_cloudflare_api_token`.       |
| `github_token`           | Forwarded to `GITHUB_TOKEN`, `GH_TOKEN`, and `TF_VAR_github_token`. |
| `region`                 | Default region for providers when `site.scaleway_region` is unset. |
| `s3_endpoint`            | Default endpoint for S3-compatible providers/backends.             |

### Secrets Management

- Store the TOML file outside version control. The CLI writes it with mode
  `0600` and only touches the `[auth]` section when persisting credentials.
- CLI flags or environment variables override `[auth]`; resolved values are
  written back so you only have to supply them once locally. In CI, skip
  persistence by passing `--no-save`.
- Temporary backend and tfvars files are generated on the fly (mode `0600`) and
  removed immediately after each command.

### One-command wrappers (pages init/plan/apply)

The `pages` CLI wraps OpenTofu with credential management and backend
bootstrapping. Only the config path (default
`~/.config/df12-www/config.toml`) and optional credential overrides are needed:

```bash
# Initialise backend/providers using config.toml
pages init --config-path ~/.config/df12-www/config.toml \
  --aws-access-key-id "$SCW_ACCESS_KEY_ID" \
  --aws-secret-access-key "$SCW_SECRET_KEY" \
  --cloudflare-api-token "$CLOUDFLARE_API_TOKEN" \
  --github-token "$GITHUB_TOKEN"

# Produce a plan (runs init automatically)
pages plan --config-path ~/.config/df12-www/config.toml --plan-file plan.out

# Apply either from a saved plan or directly from the generated tfvars
pages apply --config-path ~/.config/df12-www/config.toml --plan-file plan.out
```

What it does:

- Reads the `[auth]`, `[backend]`, and `[site]` tables from `config.toml`, then
  merges CLI/env overrides into `[auth]`.
- Generates temporary backend and tfvars files (mode `0600`), injects the
  resolved credentials, and deletes the files immediately after each command.
- Sets `AWS_*` / `SCW_*` / `TF_VAR_*` / `CLOUDFLARE_API_TOKEN` /
  `GITHUB_TOKEN` for both the backend and providers.
- Bootstraps the backend bucket if missing; SSE is disabled automatically for
  Scaleway endpoints (`encrypt = false`).
- When `cloud_provider = scaleway`, the AWS state bucket module is skipped.

Configuration path can be overridden with `DF12_CONFIG_FILE` if you prefer an
alternate location.

#### Config file example

```toml
# ~/.config/df12-www/config.toml
[auth]
aws_access_key_id = "SCW123EXAMPLE"
aws_secret_access_key = "super-secret-key"
cloudflare_api_token = "cfp_example"
github_token = "ghp_example"
region = "fr-par"
s3_endpoint = "https://s3.fr-par.scw.cloud"

[backend]
bucket = "df12-www-state"
region = "fr-par"
endpoint = "https://s3.fr-par.scw.cloud"

[site]
domain_name = "www.example.com"
root_domain = "example.com"
environment = "dev"
project_name = "df12-www"
cloud_provider = "scaleway"
cloudflare_zone_id = "0123456789abcdef0123456789abcdef"
cloudflare_proxied = true
scaleway_project_id = "31485361-39da-4ac0-bfcb-d5beb57c2c12"
scaleway_region = "fr-par"
scaleway_zone = "fr-par-1"
```

#### Cloudflare token scopes

The token used for cache purge must include, at minimum, for the target zone:

- Zone → Cache Purge (write)
- Zone → Zone (read)

If the token is missing these scopes or belongs to a different account/zone,
Cloudflare returns HTTP 403. The deploy step will now continue even if purge
fails, but use a correctly scoped token to ensure caches are cleared.

## 3. Build the Site Assets

Before planning or applying infrastructure, refresh the static assets so the
deployment module syncs the latest bundle:

```bash
bun run build
```

This pipeline:

- Compiles Tailwind into `public/assets/site.css`.
- Generates `.webp` and `.avif` variants alongside every `.png` in
  `public/images/` using `scripts/generate-image-variants.ts`.

These artifacts are intentionally `.gitignore`d; ensure they exist on disk
when running a deployment (locally or in CI) so provisioners can upload them
to the target bucket/CDN.

## 4. OpenTofu Workflow

All commands below assume the repo root as the working directory.

### AWS flow

1. **Initialize providers** (generates temporary backend/tfvars from config)

   ```bash
   pages init --config-path ~/.config/df12-www/config.toml
   ```

2. **Validate configuration**

   ```bash
   tofu fmt -check
   tofu validate
   ```

3. **Plan changes**

   ```bash
   pages plan --config-path ~/.config/df12-www/config.toml --plan-file plan.out
   ```

   Inspect the plan carefully. Expect S3 buckets, CloudFront distributions,
   ACM certificates, and Cloudflare DNS records.

4. **Apply infrastructure**

   ```bash
   pages apply --config-path ~/.config/df12-www/config.toml --plan-file plan.out
   ```

   ACM validation completes automatically through the Cloudflare DNS records.

5. **Deploy site content**
   - The `modules/deploy` module clones the repo at the desired commit,
     runs `bun install`, executes `bun run build`, and uploads the resulting
     assets with `aws s3 sync` plus a CloudFront invalidation. Ensure the
     GitHub PAT remains valid and that `site_path` points to the freshly
     built `public/` directory.

### Scaleway flow

1. Set `cloud_provider = "scaleway"` and populate the Scaleway-specific
   variables.
2. Run `pages init --config-path ~/.config/df12-www/config.toml` to fetch the
   providers and bootstrap the backend.
3. Run `pages plan --config-path ~/.config/df12-www/config.toml` and confirm the plan includes
   `scaleway_object_bucket` resources, Cloudflare CNAME records, and a
   `scaleway_cockpit` activation.
4. Run `pages apply --config-path ~/.config/df12-www/config.toml` to provision the bucket, website
   configuration, Cloudflare DNS, and Cockpit.
5. The `modules/deploy_scaleway` module clones the repo, installs
   dependencies, runs `bun run build`, syncs the `site_path` directory via
   the AWS CLI to the Scaleway S3-compatible endpoint with `--acl public-read`,
   and purges the
   Cloudflare cache so changes propagate immediately.
6. To force a fresh content upload (for example after changing ACL flags or
   build tooling), re-run `pages apply` after deleting the plan so it executes
   the deploy `null_resource` again. This re-executes the clone/build/sync/purge
   steps without touching the infrastructure resources.

## 5. CI Integration (GitHub Actions Example)

Use `deploy.tofu` as the workflow entrypoint. A minimal GitHub Actions job:

```yaml
jobs:
  deploy:
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v4
      - uses: oven-sh/setup-bun@v1
        with:
          bun-version: "1.1.21"
      - name: Install dependencies
        run: bun install
      - name: Build static assets
        run: bun run build
      - name: OpenTofu init/plan/apply
        env:
          DF12_CONFIG_FILE: ${{ secrets.DF12_CONFIG_FILE_PATH || '$HOME/.config/df12-www/config.toml' }}
          GITHUB_TOKEN: ${{ secrets.SITE_REPO_TOKEN }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        run: |
          pages init --config-path "$DF12_CONFIG_FILE" --no-save
          pages plan --config-path "$DF12_CONFIG_FILE" --plan-file plan.out --no-save
          pages apply --config-path "$DF12_CONFIG_FILE" --plan-file plan.out --no-save
```

CI tips:

- Keep the config file encrypted in CI (e.g. GitHub Actions secrets or
  workspace-scoped secrets). Provide `DF12_CONFIG_FILE` pointing to the
  decrypted path at runtime.
- Cache Bun’s package directory if builds become slow.
- Set `BUN_TMPDIR` and `BUN_INSTALL` explicitly when runner ephemeral storage
  is read-only.

## 6. Post-Deployment Verification

- **AWS:** Check the CloudFront distribution status, confirm the S3 bucket has
  new objects, and ensure AWS Budgets/CloudWatch alarms report healthy.
- **Scaleway:** Visit the bucket website endpoint (`delivery_hostname`) and
  the Cloudflare-protected URL. In the Scaleway console, verify Cockpit is
  active and billing reflects the new bucket.
- **Shared:** Confirm Cloudflare DNS records exist and cache purges succeed.

## 7. Environment Management Tips

- Maintain separate state per environment (e.g. dedicated directories or
  remote backends). The default backend is local; consider a remote backend
  for team workflows.
- Use consistent tagging (`environment`, `project_name`) to simplify cost
  tracking.
- Run `tofu test` before major changes to ensure module assertions still pass.

## 8. Content Updates & Automation

- Push changes to the configured branch; the next deployment (CI or manual)
  will rebuild assets and sync the bucket/CDN.
- Trigger a manual redeploy anytime with `tofu apply`.
- The deploy modules rely on the GitHub PAT injected at runtime. Ensure it has
  read access to the repository and rotate it periodically.

## 9. Testing and Validation

- `tofu fmt -check` — enforce formatting.
- `tofu validate` — static verification (runs offline thanks to provider mocks).
- `tofu test` — execute module unit tests located under each module’s `tests/`
  directory.

## 10. Incident Response & Rollbacks

- **Infrastructure rollback:** Use `tofu plan` against earlier revisions or
  `tofu destroy` for non-production environments. For production, prefer
  targeted `tofu apply` with version-controlled changes.
- **Content rollback:** Re-run the deploy module targeting a prior Git commit
  (e.g. update `github_branch` to a tag or SHA, or redeploy manually with the
  desired commit).
- **DNS adjustments:** Cloudflare changes propagate quickly; use their audit
  logs to revert specific records if needed.

## 11. Cleanup

To decommission all resources:

```bash
pages plan --config-path ~/.config/df12-www/config.toml --plan-file destroy.out --destroy
pages apply --config-path ~/.config/df12-www/config.toml --plan-file destroy.out
```

Confirm that S3 contents, CDN distributions, and DNS records are no longer
required before destruction.

## 12. Security Best Practices

- Enforce MFA on AWS, Scaleway, Cloudflare, and GitHub accounts used for
  deployment.
- Limit IAM permissions of credentials running OpenTofu to the minimum scope.
- Regenerate provider locks with `tofu init` per environment as needed;
  `.terraform.lock.hcl` is intentionally ignored to keep workspace artefacts
  out of the repo.
- Prefer deploy keys or GitHub App tokens for automation when possible, and
  rotate PATs on a schedule.

Following these steps ensures reproducible deployments and safe handling of
secrets across environments. Update this guide whenever configuration inputs or
provider usage changes.
