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
│   ├── episodic/
│   ├── netsuke/
│   ├── stilyagi/
│   └── weaver/
├── reference/
├── scripts/
├── src/
│   ├── static/
│   └── styles/
├── templates/
│   ├── mxd/
│   ├── episodic/
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
Sub-site output lands under path-prefixed subdirectories (`mxd/`, `episodic/`,
`netsuke/`, `weaver/`, `stilyagi/`), each containing the full static site
including assets, doc pages, and shared content pages. This directory is the
deployment root.

### `reference/`

Reference HTML snapshots and screenshots used for visual regression or
documentation illustration. `.gitignore` ignores the directory's _contents_
(`reference/*`) rather than the directory itself, so anything dropped here is
scratch by default while `index.html` can still be exempted — an ignored
directory is never descended into, so a negation for a file inside one would
never be reached. That one file is kept deliberately: a prototype homepage
themed after a cathode-ray tube (CRT) terminal, predating the generator, which
nothing in the build references.

Nothing under `reference/` is built, shipped, or linted: `biome.jsonc` excludes
the directory so that a snapshot keeps reading the way it did when it was
written rather than being churned into the house style.

### `scripts/`

Build-time scripts outside the Python package:

- `copy-static.ts` — Copies `src/static/` into `public/`, skipping the
  TypeScript sources the compile step owns.
- `compile-browser-scripts.ts` — Compiles the browser scripts under
  `src/static/**/assets/js/*.ts` to plain classic `.js` at the mirrored path
  under `public/`, with swc. It strips types only; `make typecheck` checks them.
- `generate-image-variants.ts` — Produces responsive image variants with Sharp.
- `build-netsuke-search-index.mjs` — Builds the MiniSearch full-text index for
  the Netsuke documentation sub-site.

### `src/`

Frontend source files. `styles/` contains one Tailwind CSS entry point per
compiled site — `site.css` for the main site, and `mxd.css`, `episodic.css`,
`weaver.css` and `stilyagi.css` for those sub-sites — plus any plugins. Each is
compiled to its own file under `public/`: `public/assets/site.css`,
`public/mxd/assets/tailwind.css`, `public/episodic/assets/styles/tailwind.css`,
`public/weaver/assets/styles/weaver.css`, and
`public/stilyagi/assets/styles/stilyagi.css`.

An entry point that has grown past a single file keeps its partials in a
directory beside it. `styles/episodic/`, `styles/weaver/` and
`styles/stilyagi/` are the examples: the entry point declares the theme and
imports partials named for what they style, each into an explicit cascade layer.

`static/` holds the hand-crafted assets — stylesheets, scripts, images, fonts,
and favicons — that are published at the same path. Its layout mirrors the
output, so `src/static/stilyagi/assets/fonts/` is published at
`/stilyagi/assets/fonts/`. Most files are copied verbatim; the browser scripts
under `static/<site>/assets/js/` are TypeScript, typechecked against
`tsconfig.browser.json` and compiled to `.js` at the mirrored path, and
`static/browser-globals.d.ts` declares the globals those classic scripts can
see beyond the DOM. Edit the files here. The copies under `public/` are build
output and are overwritten on the next build. The one stylesheet still under
`src/static/stilyagi/assets/styles/` is `syntax.css`, whose marked block is
generated Pygments output; it compiles into the Stilyagi entry point rather
than being linked on its own.

### `templates/`

Per-sub-site Jinja template sets. Each subdirectory (`mxd/`, `episodic/`,
`netsuke/`, `weaver/`, `stilyagi/`) holds the templates for that sub-site's
design system. Episodic and Netsuke keep shared macros in `components.jinja`;
Netsuke adds `chrome.jinja` for page furniture, `docs_nav.jinja` for the docs
navigation, and `examples_data.jinja` for the examples catalogue, and every
Netsuke content page and the homepage extend `doc_page.jinja`; the one
standalone document is `pages/icon-replacements.jinja`, which carries its own
head and scripts. Stilyagi centralizes its chrome in `_layout.jinja` that
every page extends.
These are distinct from the main-site templates in `df12_pages/templates/`.

### `tests/`

Test suite for the Python package:

- `bdd/` — Step definition modules that implement the Gherkin scenarios in
  `features/`.
- `cassettes/` — Betamax HTTP recording cassettes for reproducible API tests.
- Top-level test modules cover doc generation, docs index rendering, release
  bumping, and the deployment subsystem.

## Top-level configuration files

| File                       | Purpose                                                        |
| -------------------------- | -------------------------------------------------------------- |
| `Makefile`                 | Build, lint, format, and test orchestration                    |
| `package.json`             | Node/Bun scripts and frontend dependencies                     |
| `pyproject.toml`           | Python project metadata and tool configuration                 |
| `uv.lock`                  | Locked Python dependency graph                                 |
| `bun.lockb`                | Locked Node dependency graph                                   |
| `biome.jsonc`              | Biome linter and formatter configuration                       |
| `tsconfig.json`            | TypeScript solution file referencing the two projects below    |
| `tsconfig.base.json`       | Strict compiler options shared by both projects                |
| `tsconfig.browser.json`    | Typechecks the browser scripts under `src/static/`             |
| `tsconfig.scripts.json`    | Typechecks `scripts/` and the Tailwind plugin; read by TypeDoc |
| `typedoc.json`             | TypeDoc documentation gate configuration                       |
| `.markdownlint-cli2.jsonc` | Markdownlint rule overrides and ignores                        |
| `*.tofu`                   | OpenTofu infrastructure definitions                            |
| `AGENTS.md`                | Agent and contributor workflow instructions                    |

_Table 1: Top-level configuration files and their responsibilities._
