# df12 OpenTofu Site

This repository contains the configuration for a static website deployment using [OpenTofu](https://opentofu.org). Infrastructure components are defined in modules under `modules/`.

## Deployment Overview

The `modules/deploy` script automates publishing site content:

1. It clones the specified GitHub repository and extracts the latest commit ID.
2. When the commit changes, it syncs the local `site` directory to the S3 bucket created by the stack.
3. After uploading, it invalidates the CloudFront distribution so that visitors receive the newest files.

See [docs/deploy.md](docs/deploy.md) for detailed configuration steps and options.

This project is released under the [GNU Affero General Public License v3.0](LICENSE).
