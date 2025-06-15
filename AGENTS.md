# Contributor Guide

This repository manages a sample website using **OpenTofu**. The top-level deployment entrypoint is `deploy.tofu`. Reusable modules live under `modules/` (e.g., `modules/static_site`, `modules/deploy`, `modules/monitoring`). Module tests reside inside each module's `tests/` directory. Additional documentation is provided in `docs/`, including:

- `docs/opentofu-hcl-syntax-guide.md` – HCL style, block structure, and formatting conventions.
- `docs/opentofu-module-unit-testing-guide.md` – instructions for unit testing modules with the OpenTofu native framework.

## Formatting and Validation

Whenever modifying `.tofu` or `.tf` files, run:

```bash
tofu fmt -check
tofu validate
tofu test
```

These commands ensure consistent style, validate syntax, and execute unit tests. See the unit testing guide for details on setting up and running tests.

## Development Workflow

Changes to `deploy.tofu` or any module should be tested with the OpenTofu native framework as described in `docs/opentofu-module-unit-testing-guide.md`. Follow the standard workflow of `tofu init`, `tofu plan`, and `tofu apply` (or CI equivalents) when updating infrastructure.

## Commit Messages

Use concise, conventional titles such as:

- `feat: add new monitoring alarms`
- `fix: correct bucket policy`

Mention the affected module or script in the body if necessary.

For further background, consult the `docs/` directory before making significant changes.
