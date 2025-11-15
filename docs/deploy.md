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

Create a `terraform.tfvars` file per environment (e.g. `terraform.tfvars.dev`)
and populate the required variables:

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

### Secrets Management

- Store secrets (GitHub token, optional GitHub SSH private key, Cloudflare token, provider credentials) outside
  version control.
  - Pass them as environment variables when running commands locally:
    `tofu plan -var="github_token=$GITHUB_TOKEN"` or
    `tofu plan -var="github_ssh_private_key=$(cat ~/.ssh/id_ed25519)"`.
  - Keep encrypted `.tfvars` files using tools such as `sops` if you must
    persist them.
  - In CI, rely on the platform’s secrets store (e.g. GitHub Actions secrets)
    and inject them at runtime.
- `.gitignore` already excludes `*.tfvars` and `.terraform/`.
- Rotate tokens regularly and scope them to the minimum required access.

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

1. **Initialize providers**

   ```bash
   tofu init
   ```

2. **Validate configuration**

   ```bash
   tofu fmt -check
   tofu validate
   ```

3. **Plan changes**

   ```bash
   tofu plan -var-file="terraform.tfvars.prod"
   ```

   Inspect the plan carefully. Expect S3 buckets, CloudFront distributions,
   ACM certificates, and Cloudflare DNS records.

4. **Apply infrastructure**

   ```bash
   tofu apply -var-file="terraform.tfvars.prod"
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
2. Run `tofu init` to fetch the Scaleway provider alongside the others.
3. Run `tofu plan -var-file=...` and confirm the plan includes
   `scaleway_object_bucket` resources, Cloudflare CNAME records, and a
   `scaleway_cockpit` activation.
4. Run `tofu apply -var-file=...` to provision the bucket, website
   configuration, Cloudflare DNS, and Cockpit.
5. The `modules/deploy_scaleway` module clones the repo, installs
   dependencies, runs `bun run build`, syncs the `site_path` directory via
   the AWS CLI to the Scaleway S3-compatible endpoint with `--acl public-read`,
   and purges the
   Cloudflare cache so changes propagate immediately.
6. To force a fresh content upload (for example after changing ACL flags or
   build tooling), re-run apply with the deploy resource replaced:
   ```bash
   tofu apply -var-file="terraform.tfvars.prod" \
     -replace="module.deploy_scaleway[0].null_resource.deploy"
   ```
   This re-executes the clone/build/sync/purge steps without touching the
   infrastructure resources.

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
          GITHUB_TOKEN: ${{ secrets.SITE_REPO_TOKEN }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        run: |
          tofu init
          tofu plan -var-file="terraform.tfvars.prod"
          tofu apply -auto-approve -var-file="terraform.tfvars.prod"
```

CI tips:

- Store environment-scoped `terraform.tfvars.*` securely (encrypted secrets,
  object storage with KMS, etc.).
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
tofu destroy -var-file="terraform.tfvars.prod"
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
