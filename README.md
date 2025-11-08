# df12 OpenTofu Site

This repository contains the configuration for **my** static website deployment
using [OpenTofu](https://opentofu.org). It is not meant as a generic template.
Infrastructure components are defined in modules under `modules/`.

## Deployment Overview

The `modules/deploy` script automates publishing site content:

1. It clones the specified GitHub repository and extracts the latest commit ID.
2. The contents of the cloned repository are placed in the local `site`
   directory.
3. When the commit changes, it syncs the `site` directory to the S3 bucket
   created by the stack.
4. After uploading, it invalidates the CloudFront distribution so that visitors
   receive the newest files.
5. A GitHub Actions workflow (coming soon) will automatically run this script
   whenever new commits are pushed.

See [docs/deploy.md](docs/deploy.md) for detailed configuration steps and
options.

## Documentation pages

The `df12_pages` package fetches remote Markdown sources, parses each
second-level section, and renders Tailwind/DaisyUI themed HTML into `public/`.
Page-specific metadata (source URL, layout devices, theming) lives in
`config/pages.yaml`, which now supports multiple page bundles.

To refresh the docs, install the Python requirements (or rely on the embedded
`uv` metadata) and run the `pages` CLI:

```bash
pip install -r requirements.txt  # optional when not using `uv run`
uv run pages generate --page netsuke
```

The CLI uses Cyclopts and honours `INPUT_`-prefixed environment variables such
as `INPUT_PAGE`, `INPUT_CONFIG`, and `INPUT_OUTPUT_DIR`. Each page entry defines
its layouts, so files like `public/docs-netsuke-getting-started.html` continue
to match the visual system established by `public/index.html` while enabling
future additions without touching Python.

This project is released under the
[GNU Affero General Public License v3.0](LICENSE).
