# Deploying the Static Site with OpenTofu

This guide explains how to use the OpenTofu configuration in this repository to publish a static website. The process uses AWS S3 for storage, CloudFront for CDN, and a GitHub repository as the source of content.

## Prerequisites

- [OpenTofu](https://opentofu.org/) installed on your local machine.
- [AWS CLI](https://aws.amazon.com/cli/) configured with credentials that can create S3 buckets, CloudFront distributions and other resources.
- A personal access token for the GitHub repository containing your site files.

## Configuration

1. **Clone this repository** and change into its directory.
2. Edit `variables.tofu` or create a `terraform.tfvars` file to provide values for the required variables:
   - `domain_name` – fully qualified domain (e.g. `www.example.com`).
   - `root_domain` – apex domain (e.g. `example.com`).
   - `github_owner` and `github_repo` – location of the site source.
   - `github_token` – GitHub PAT used by the `deploy` module.
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

After the first apply, the `modules/deploy` script tracks commits in the specified GitHub repository. Each time the commit hash changes, it synchronizes the `site` directory with the S3 bucket and invalidates the CloudFront cache so that new content becomes available immediately.

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
