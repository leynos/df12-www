# df12 OpenTofu Site

This repository contains the configuration for **my** static website deployment using [OpenTofu](https://opentofu.org). It is not meant as a generic template. Infrastructure components are defined in modules under `modules/`.

## Deployment Overview

The `modules/deploy` script automates publishing site content:

1. It clones the specified GitHub repository and extracts the latest commit ID.
2. The contents of the cloned repository are placed in the local `site` directory.
3. When the commit changes, it syncs the `site` directory to the S3 bucket created by the stack.
4. After uploading, it invalidates the CloudFront distribution so that visitors receive the newest files.
5. A GitHub Actions workflow (coming soon) will automatically run this script whenever new commits are pushed.

See [docs/deploy.md](docs/deploy.md) for detailed configuration steps and options.

This project is released under the [GNU Affero General Public License v3.0](LICENSE).
