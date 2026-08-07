# Repository layout

This document describes the directory structure of the df12-www repository and
the responsibilities of each major path. The tree below is simplified;
generated artefacts and tool caches are omitted for clarity.

```plaintext
df12-www/
├── config/
│   ├── pages.yaml
│   └── shared/
├── df12_pages/
│   ├── config/
│   ├── generator/
│   └── templates/
├── docs/
│   └── execplans/
├── features/
├── modules/
├── public/
│   ├── mxd/
│   ├── netsuke/
│   ├── stilyagi/
│   └── weaver/
├── reference/
├── scripts/
├── src/
│   └── styles/
├── templates/
│   ├── mxd/
│   ├── netsuke/
│   ├── stilyagi/
│   └── weaver/
├── tests/
│   ├── bdd/
│   └── cassettes/
├── Makefile
├── package.json
├── pyproject.toml
└── *.tofu
```

## Top-level directories

### `config/`

Site generation configuration. `pages.yaml` is the single source of truth for
page definitions, sub-site declarations, shared content references, homepage
layout, and theme settings. The `shared/` subdirectory holds Markdown source
files for legal pages (terms of use, privacy policy, code of conduct) that are
rendered into every site through each site's own template wrapper.

### `df12_pages/`

The Python package that powers the `pages` CLI. Contains the site generator,
config loader, Markdown parser, and all builder classes. Key subdirectories:

- `config/` — Dataclass models, YAML loader, and config helpers.
- `generator/` — Page rendering pipeline: section models, HTML renderer, link
  rewriter, and the `PageContentGenerator` orchestrator.
- `templates/` — Jinja templates for the main df12 site (doc pages, docs index,
  homepage, about page, shared content wrapper).

### `docs/`

Project documentation, design documents, and reference guides. Includes
Tailwind migration guides, OpenTofu coding standards, the documentation style
guide, and deployment notes.

- `execplans/` — Execution plans for non-trivial repository changes.

### `features/`

Gherkin feature files for behaviour-driven tests. Each `.feature` file
describes acceptance scenarios exercised by the corresponding step definitions
in `tests/bdd/`.

### `modules/`

OpenTofu modules for infrastructure provisioning. Each subdirectory is a
self-contained module (static site hosting, state bucket, monitoring,
Scaleway-specific variants, and deployment configuration).

### `public/`

Generated output directory. The main df12 site pages live at the top level.
Sub-site output lands under path-prefixed subdirectories (`mxd/`, `netsuke/`,
`weaver/`, `stilyagi/`), each containing the full static site including
assets, doc pages, and shared content pages. This directory is the deployment root.

### `reference/`

Reference HTML snapshots and screenshots used for visual regression or
documentation illustration.

### `scripts/`

Build-time scripts outside the Python package:

- `generate-image-variants.ts` — Produces responsive image variants with Sharp.
- `build-netsuke-search-index.mjs` — Builds the MiniSearch full-text index for
  the Netsuke documentation sub-site.

### `src/`

Frontend source files. `styles/` contains the Tailwind CSS entry point (
`site.css`) and any plugins. The compiled output is written to
`public/assets/site.css`.

### `templates/`

Per-sub-site Jinja template sets. Each subdirectory (`mxd/`, `netsuke/`,
`weaver/`, `stilyagi/`) holds the template wrapper for that sub-site's design
system, including `shared_content_page.jinja` and a `partials/` directory for
shared macros and components. Stilyagi instead centralizes its chrome in a
`_layout.jinja` that every page extends. These are distinct from the main-site
templates in `df12_pages/templates/`.

### `tests/`

Test suite for the Python package:

- `bdd/` — Step definition modules that implement the Gherkin scenarios in
  `features/`.
- `cassettes/` — Betamax HTTP recording cassettes for reproducible API tests.
- Top-level test modules cover doc generation, docs index rendering, release
  bumping, and the deployment subsystem.

## Top-level configuration files

| File                       | Purpose                                        |
| -------------------------- | ---------------------------------------------- |
| `Makefile`                 | Build, lint, format, and test orchestration    |
| `package.json`             | Node/Bun scripts and frontend dependencies     |
| `pyproject.toml`           | Python project metadata and tool configuration |
| `uv.lock`                  | Locked Python dependency graph                 |
| `bun.lockb`                | Locked Node dependency graph                   |
| `biome.jsonc`              | Biome linter and formatter configuration       |
| `.markdownlint-cli2.jsonc` | Markdownlint rule overrides and ignores        |
| `*.tofu`                   | OpenTofu infrastructure definitions            |
| `AGENTS.md`                | Agent and contributor workflow instructions    |

_Table 1: Top-level configuration files and their responsibilities._
