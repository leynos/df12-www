# Deploying the Static Site with OpenTofu

This guide explains how to use the OpenTofu configuration in this repository to publish **your** website. It is tailored to this project and not meant as a one-size-fits-all example. The process uses AWS S3 for storage, CloudFront for CDN, and a GitHub repository as the source of content.

## Prerequisites

 - [OpenTofu](https://opentofu.org/) **v1.6** or newer installed locally.
- [AWS CLI](https://aws.amazon.com/cli/) **v2.0** or newer configured with credentials that can create S3 buckets, CloudFront distributions and other resources.
 - A personal access token for the GitHub repository containing the site files. The deployment module uses a temporary Git configuration include to inject an HTTP Authorization header during `git clone`, avoiding exposure of credentials in process arguments.

## Configuration

1. **Clone this repository** and change into its directory:
   ```bash
   git clone git@github.com:leynos/df12-www.git
   cd df12-www
   ```
2. Create a `terraform.tfvars` file (or edit `variables.tf`) to provide values for the required variables (see `terraform.tfvars.example` for guidance):
   - `domain_name` – fully qualified domain (e.g. `www.example.com`).
   - `root_domain` – apex domain (e.g. `example.com`).
   - `github_owner` and `github_repo` – location of the site source.
   - `github_token` – GitHub PAT used by the `deploy` module for authenticated cloning.
   - `budget_email` – address for cost alerts.
3. Optionally adjust defaults such as the AWS region or log retention days.

## Running the Deployment

1. Initialize the working directory:

   ```bash
   tofu init
   ```
2. Review the planned actions:

   ```bash
   tofu plan
   ```
3. Apply the configuration to create the infrastructure:

   ```bash
   tofu apply
   ```

After the first apply, a forthcoming GitHub Actions workflow will monitor the repository for new commits. When it detects a change, it runs the `modules/deploy` script which syncs the `site` directory to the S3 bucket and invalidates the CloudFront cache so visitors see the updated content immediately.

## Updating Content

Push changes to the configured branch of your GitHub repository. The next run of the deployment will detect the new commit and publish the updated site automatically. You can trigger the sync manually by running `tofu apply` again.

## Testing and Validation

The repository includes unit tests under each module's `tests/` directory. Run `tofu test` to execute them. Formatting and syntax can be verified with `tofu fmt -check` and `tofu validate`.

## Cleanup

To remove all resources created by this configuration, run:

```bash
tofu destroy
```

Ensure you no longer need the S3 bucket contents or any CloudFront distributions before destroying.
