# Deployment Guide — df12 Static Site

_Updated: 23 October 2025_

This guide explains how to configure, build, and deploy the df12 static site
using the OpenTofu infrastructure stack. It also calls out best practices for
managing secrets and environment-specific overrides.

## 1. Prerequisites

- **Tooling**
  - [Bun](https://bun.sh) ≥ 1.1 for building the Tailwind bundle.
  - [OpenTofu CLI](https://opentofu.org) ≥ 1.6.0.
  - AWS CLI (for manual verification or troubleshooting when targeting AWS).
  - Optional: Scaleway CLI (`scw`) for ad-hoc diagnostics when targeting Scaleway.
- **Accounts & credentials**
  - AWS account with permissions to manage S3, CloudFront, ACM, IAM, and
    Budgets (required when `cloud_provider = "aws"`).
  - Scaleway project with Object Storage and Cockpit access rights (required
    when `cloud_provider = "scaleway"`). Create API access/secret keys with
    project-level scope.
  - Cloudflare account with access to the DNS zone that will host the site.
  - GitHub repository containing the site source (this repo) and a personal
    access token for cloning.
- **Local environment**
  - Clone the repo.
  - Install dependencies: `bun install`.

## 2. Configuration Inputs

Fill out a copy of `terraform.tfvars` for each environment (e.g.
`terraform.tfvars.dev`). The key variables are:

| Variable                                       | Purpose                                                                                   |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `domain_name`                                  | Fully qualified domain that will serve the site (e.g. `www.example.com`).                 |
| `root_domain`                                  | Apex domain used for DNS validation (e.g. `example.com`). Must match the Cloudflare zone. |
| `aws_region`                                   | Region for S3 buckets and logging (defaults to `eu-west-2`).                              |
| `environment`                                  | Environment label used in tagging (e.g. `dev`, `prod`).                                   |
| `project_name`                                 | Tag prefix for identifying resources (defaults to `df12-www`).                            |
| `github_owner`, `github_repo`, `github_branch` | Repository information for fetching the built site.                                       |
| `github_token`                                 | Personal access token with `repo` scope for authenticated git clones. Treat as sensitive. |
| `site_path`                                    | Relative path to the built static site (defaults to `public`).                            |
| `cloudflare_api_token`                         | API token with DNS edit permissions for the zone.                                         |
| `cloudflare_zone_id`                           | 32-character Cloudflare zone identifier for `root_domain`.                                |
| `cloudflare_proxied`                           | Set to `true` to enable Cloudflare proxying for the CDN CNAME.                            |
| `cloud_provider`                               | Either `aws` or `scaleway` (defaults to `aws`).                                           |
| `budget_limit_gbp`                             | Monthly AWS budget threshold in GBP for cost alerts.                                      |
| `budget_email`                                 | Email address that receives AWS/Scaleway alert notifications.                             |
| `log_retention_days`                           | CloudFront log retention (defaults to 14 days, ignored on Scaleway).                      |

If `cloud_provider = "scaleway"`, populate the additional variables:

| Variable                    | Purpose                                                             |
| --------------------------- | ------------------------------------------------------------------- |
| `scaleway_access_key`       | API access key with permissions for Object Storage and Cockpit.     |
| `scaleway_secret_key`       | Secret key paired with the access key.                              |
| `scaleway_project_id`       | Project UUID that owns the static assets.                           |
| `scaleway_organization_id`  | Optional organization UUID (leave empty for project-scoped access). |
| `scaleway_region`           | Object Storage region (e.g. `fr-par`).                              |
| `scaleway_zone`             | Service zone (e.g. `fr-par-1`).                                     |

### Secrets Management

- Store secrets (GitHub token, Cloudflare token) outside version control.
  Recommended approaches:
  - Pass them as environment variables and reference in CLI commands
    (`tofu plan -var="github_token=$GITHUB_TOKEN"`).
  - Keep encrypted `.tfvars` files using tools like `sops` if you must persist
    them locally.
  - In CI, use the platform’s secrets store (e.g. GitHub Actions secrets) and
    inject them at runtime.
- Never commit `terraform.tfvars` files containing credentials. `.gitignore`
  already excludes `*.tfvars`.
- Rotate tokens regularly and scope them to the minimum required permissions:
  - Cloudflare token: DNS edit + zone read for the target zone.
  - GitHub PAT: `repo` scope limited to read access on the site repo.

## 3. Build the Site Assets

Before deploying, ensure the compiled CSS is up-to-date:

```bash
bun run build
```

This generates `public/assets/site.css`. Commit the output if you maintain
built assets in source control; otherwise ensure the deploy module pulls the
latest build artifacts.

## 4. OpenTofu Workflow

All commands below assume the repo root as the working directory.

### AWS flow

1. **Initialize providers**

   ```bash
   tofu init
   ```

   This downloads the AWS, Cloudflare, GitHub, and Scaleway providers and
   creates `.terraform.lock.hcl`.

2. **Validate configuration**

   ```bash
   tofu fmt -check
   tofu validate
   ```

   The validation step can run offline thanks to provider mocks in the module
   tests.

3. **Plan changes**

   ```bash
   tofu plan -var-file="terraform.tfvars.prod"
   ```

   Inspect the plan carefully. For AWS, look for S3 buckets, CloudFront
   distributions, ACM certificates, and Cloudflare DNS records.

4. **Apply infrastructure**

   ```bash
   tofu apply -var-file="terraform.tfvars.prod"
   ```

   This provisions or updates all infrastructure. ACM validation completes
   automatically via the Cloudflare DNS records.

5. **Deploy site content**
   - The `modules/deploy` module clones the repo at the specified commit and
     runs `aws s3 sync` plus a CloudFront invalidation. Ensure the GitHub PAT
     remains valid and that `site_path` contains the built `index.html`,
     `assets/`, and `images/` directories.

### Scaleway flow

The workflow mirrors AWS with a few provider-specific changes:

1. Set `cloud_provider = "scaleway"` and populate the Scaleway variables.
2. Run `tofu init` to fetch the Scaleway provider alongside the others.
3. Run `tofu plan -var-file=...` and confirm the plan includes
   `scaleway_object_bucket` resources, Cloudflare CNAME records, and a
   `scaleway_cockpit` activation.
4. Run `tofu apply -var-file=...` to provision the bucket, website
   configuration, Cloudflare DNS, and Cockpit.
5. The `modules/deploy_scaleway` module syncs the `site_path` directory using
   AWS CLI against the Scaleway S3-compatible endpoint and purges the
   Cloudflare cache so changes propagate immediately.

## 5. Post-Deployment Verification

- **AWS:** Check the CloudFront distribution status, confirm the bucket has
  new objects, and ensure AWS Budgets/CloudWatch alarms report healthy.
- **Scaleway:** Visit the bucket website endpoint (exposed in
  `delivery_hostname`) and the Cloudflare-protected URL to confirm content.
  In the Scaleway console, verify Cockpit is active and invoices reflect the
  new bucket.
- For either provider, ensure Cloudflare lists the expected CNAME records and
  that cache purges succeed.

## 6. Environment Management Tips

- Maintain separate state files per environment by using different directories
  or backends (e.g. `prod/tofu init`). The default backend is local; consider
  storing state in a secure remote backend for team environments.
- Use consistent naming conventions and tagging (`environment`, `project_name`)
  to simplify cost reporting.
- Run `tofu test` before large changes to ensure module assertions still pass.

## 7. Incident Response & Rollbacks

- **Infrastructure rollback** – Use `tofu plan` with previous state or
  `tofu destroy` for non-production environments. For production, prefer
  targeted `tofu apply` with version-controlled configuration.
- **Content rollback** – Re-run the deploy module pointing at a prior Git
  commit (e.g. update `github_branch` to a tag or SHA, or run the provisioner
  manually with the desired commit).
- **DNS adjustments** – Cloudflare changes propagate quickly; use Cloudflare’s
  audit logs to track modifications and revert individual records when
  necessary.

## 8. Security Best Practices

- Enforce MFA on AWS, Scaleway, Cloudflare, and GitHub accounts used for
  deployment.
- Limit IAM permissions of the AWS credentials running OpenTofu to only the
  services required.
- Store `.terraform.lock.hcl` under version control to guarantee provider
  pinning and reproducible plans.
- Review GitHub PAT scopes and prefer deploy keys or GitHub App tokens for
  automation where possible.

Following these steps ensures reproducible deployments and safe handling of
secrets across environments. Update this guide whenever configuration inputs or
provider usage changes. When using Scaleway, monitor Cockpit’s cost dashboard
and configure additional alert channels from Grafana if you need granular
usage notifications or DDoS detection.
