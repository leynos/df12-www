# Contributor Guide

This repository manages a sample website using **OpenTofu**. The top-level
deployment entrypoint is `deploy.tofu`. Reusable modules live under `modules/`
(e.g., `modules/static_site`, `modules/deploy`, `modules/monitoring`). Module
tests reside inside each module's `tests/` directory. Additional documentation
is provided in `docs/`, including:

- [OpenTofu Coding Standards](docs/opentofu-coding-standards.md) – project-wide
  conventions and best practices.
- [HCL Syntax Guide](docs/opentofu-hcl-syntax-guide.md) – HCL style, block
  structure, and formatting conventions.
- [Module Unit-Testing Guide](docs/opentofu-module-unit-testing-guide.md) –
  instructions for unit testing modules with the OpenTofu native framework.

## Formatting and Validation

Whenever modifying `.tofu` or `.tf` files, run:

```bash
tofu fmt -check
tofu validate
tofu test
```

These commands ensure consistent style, validate syntax, and execute unit
tests. See the unit testing guide for details on setting up and running tests.

For Markdown changes, run `make markdownlint` and `make nixie`. The Markdown
gate refreshes the shared en-GB-oxendict base, regenerates `typos.toml`, and
checks maintained prose with the pinned `typos` release. Put narrow
repository-only exceptions in `typos.local.toml`; never edit the generated
configuration by hand.

### Variable Declarations

All input variables must include at least a `description` and `type` argument.
If a variable is required, set `nullable = false`. Document `default` values
and mark `sensitive = true` when appropriate so that callers understand the
module interface.

### Offline Validation

`tofu validate` should run without network access. Stub out any provider calls
or HTTP requests during validation (for example via `mock_provider` blocks) so
that the configuration can be validated offline.

## Python docstring guidance

- **Document public APIs comprehensively.** Public functions, classes, and
  methods must have comprehensive NumPy-style docstrings, including clear
  examples that demonstrate usage and outcome where appropriate.
- **Keep private helper docstrings concise.** Prefer single-line docstrings for
  private helpers. When a private helper needs an explanatory paragraph,
  inspect whether that need exposes conflated responsibilities, an unclear
  command/query boundary, or another CQRS or cohesion failure:
  - Split the helper when it performs distinct query and command
    responsibilities or combines unrelated concerns.
  - Extract a focused helper when doing so makes the invariant or boundary
    local and simpler.
  - Keep the helper intact when its responsibility is cohesive and the
    explanation documents an unavoidable local constraint; retain the
    paragraph in that case.
- **Structure private helper docstrings selectively.** Use structured
  NumPy-style sections for private helpers only when they describe non-obvious
  behaviour.
- **Keep test documentation meaningful.** Test documentation should omit
  examples that only restate the test logic.

## Development Workflow

Test any changes to `deploy.tofu` or its modules using the OpenTofu native
framework as described in `docs/opentofu-module-unit-testing-guide.md`. Follow
the standard workflow of `tofu init`, `tofu plan`, and `tofu apply` (or CI
equivalents) when updating infrastructure.

## Commit Messages

Use concise, conventional titles such as:

- `feat: add new monitoring alarms`
- `fix: correct bucket policy`

Mention the affected module or script in the body if necessary.

For more details, see the
[Conventional Commits](https://www.conventionalcommits.org/) specification.

For further background, consult the `docs/` directory before making significant
changes.
