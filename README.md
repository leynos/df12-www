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

## Netsuke documentation pages

The `scripts/netsuke_docs/` library fetches the upstream Netsuke user guide,
parses each second-level section, and renders Tailwind/DaisyUI themed HTML into
`public/`. The layouts for special sections (numbered steps, split code/text
panels, etc.) live in `docs/netsuke-section-layouts.yaml` so designers can tweak
them without touching Python.

To refresh the docs, install the Python requirements (or rely on the embedded
`uv` metadata) and run the generator:

```bash
pip install -r requirements.txt  # optional when not using `uv run`
uv run scripts/generate_netsuke_docs.py
```

The CLI uses Cyclopts and honours environment variables prefixed with
`INPUT_`. For example, `INPUT_OUTPUT_DIR=dist uv run scripts/generate_netsuke_docs.py`
will emit to `dist/`. By default, files such as
`public/docs-netsuke-getting-started.html` share the same design language as
`public/index.html` and automatically pick up Pygments styling for fenced code
blocks.

This project is released under the
[GNU Affero General Public License v3.0](LICENSE).
