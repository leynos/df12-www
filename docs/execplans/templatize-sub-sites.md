# Templatize sub-sites: mxd homepage, weaver, and netsuke

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
 `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`,
and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Status: IN PROGRESS

## Purpose / big picture

Three sub-sites — mxd, weaver, and netsuke — exist as static HTML in
`public/{site}/`. The build pipeline (`df12_pages`) can already generate pages
from Jinja2 templates, but the hard-coded files in `public/` pre-date this
system and bypass it entirely.

After this work, every HTML page across all three sub-sites will be produced by
`pages generate --site {site}` from templates in `templates/{site}/`. The
`public/` directories will contain only generated output plus non-HTML assets
(images, CSS, JS). No hand-authored HTML will remain in `public/`.

Observable success: running `pages generate --site mxd` (and weaver, netsuke)
regenerates all HTML identically to what exists today, validated visually via
Playwright screenshots and structurally via
`make fmt check-fmt typecheck lint test` passing clean.

## Constraints

- The visual appearance of every page must be preserved exactly. No design
  changes are permitted as part of this migration.
- The pipeline (`df12_pages`) Python source must remain passing all existing
  tests after any code changes.
- No new external Python dependencies may be introduced.
- The hard-coded `public/{site}/index.html` files and all other hard-coded
  content HTML files must be deleted once their templates produce identical
  output. Asset files (images, CSS, JS) in `public/` are not templates and must
  not be deleted.
- No changes to the deployment pipeline (`deploy/`, `*.tofu`) are permitted.
- The `templates/{site}/shared_content_page.jinja` templates already exist and
  work correctly; do not alter them.
- Commit after each stage. Gate each commit with `make fmt check-fmt typecheck
  lint test` (run sequentially, not in parallel).

## Tolerances (exception triggers)

- Scope: if any single stage requires touching more than 30 files, stop and
  re-scope.
- Interface: if a public function or class signature in `df12_pages/` must
  change beyond adding optional keyword parameters, stop and escalate.
- Iterations: if `make test` still fails after 3 fix attempts on any one
  failure, stop and escalate.
- Visual: if a Playwright screenshot reveals an unintended visual difference
  versus the reference (hard-coded page), stop and investigate before
  proceeding.
- Ambiguity: if a page's layout relies on behaviour not yet supported by the
  build pipeline (e.g., a page type with no suitable base template), document
  the gap and escalate.

## Risks

- Risk: `SubSiteHomePageBuilder` does not pass `nav_links` or `parent_link` to
  templates, so homepages cannot render shared navigation. Severity: medium
  Likelihood: high (confirmed from code review) Mitigation: Extend
  `SubSiteHomePageBuilder.__init__` with optional `nav_links` and `parent_link`
  kwargs and include them in the render context. Update `cli.py` to pass them
  from the `SubSiteConfig`. This is a small, additive Python change.

- Risk: Weaver and netsuke `nav_links` in `pages.yaml` use relative hrefs
  (`../`), which `ContentPageGenerator._mark_current_nav()` cannot match
  against absolute `target_href` values. Severity: low (nav "current" marking
  would silently fail, not break pages) Likelihood: high (confirmed from code
  review) Mitigation: Update weaver and netsuke `nav_links` in `pages.yaml` to
  use absolute paths (`/weaver/...`, `/netsuke/...`) before wiring up content
  pages.

- Risk: Nested output slugs (e.g., `docs/getting-started`) may not be handled
  correctly by `ContentPageGenerator` or `_mark_current_nav`. Severity: medium
  Likelihood: low (`output_dir / output_slug / "index.html"` handles path
  separators in slugs correctly on Linux) Mitigation: Verify by running the
  generator for one nested slug before wiring up all pages.

- Risk: Weaver and netsuke pages use Tailwind CDN and FontAwesome CDN inline
  in each page, not a compiled stylesheet. This pattern is fine in templates
  but adds ~400 bytes of `<script>`/`<link>` tags to the base template.
  Severity: low Likelihood: certain (by design) Mitigation: Replicate these CDN
  tags verbatim in the `doc_page.jinja` base template for each site. No action
  needed.

- Risk: The weaver homepage uses an inline `<script>` block for Tailwind
  configuration that differs in detail from sub-pages (no differences found on
  inspection, but confirm during implementation). Severity: low Likelihood: low
  Mitigation: Confirm the Tailwind config block is identical across all weaver
  pages; if not, move differing parts into the page-level block.

## Progress

- [x] (2026-05-05) Stage 1: mxd homepage
  - [x] (2026-05-05) Extend `SubSiteHomePageBuilder` and update `cli.py`
  - [x] (2026-05-05) Create `templates/mxd/home_page.jinja`
  - [x] (2026-05-05) Add `homepage:` key to `sites.mxd` in `config/pages.yaml`
  - [x] (2026-05-05) Run `pages generate --site mxd`, validate, delete
        `public/mxd/index.html`
  - [x] (2026-05-05) Gate commit (`8c11192`)

- [x] (2026-05-05) Stage 2: weaver (14 pages)
  - [x] (2026-05-05) Update weaver `nav_links` to absolute paths in
        `config/pages.yaml`
  - [x] (2026-05-05) Create `templates/weaver/doc_page.jinja`
  - [x] (2026-05-05) Create `templates/weaver/home_page.jinja`
  - [x] (2026-05-05) Create 13 page templates in `templates/weaver/pages/`
  - [x] (2026-05-05) Add `homepage:` and `content_pages:` to `sites.weaver` in
        `config/pages.yaml`
  - [x] (2026-05-05) Run `pages generate --site weaver`, validate (Playwright
        screenshots confirm correct rendering), all 17 pages generated
  - [x] (2026-05-05) Gate commit (this commit)

- [ ] Stage 3: netsuke (20 pages)
  - [ ] Update netsuke `nav_links` to absolute paths in `config/pages.yaml`
  - [ ] Create `templates/netsuke/doc_page.jinja`
  - [ ] Create `templates/netsuke/home_page.jinja`
  - [ ] Create 19 page templates in `templates/netsuke/pages/`
  - [ ] Add `homepage:` and `content_pages:` to `sites.netsuke` in
        `config/pages.yaml`
  - [ ] Run `pages generate --site netsuke`, validate, delete 20
        hard-coded HTML files
  - [ ] Gate commit

## Surprises & discoveries

- Observation: Weaver page templates created by the Task agent used
  `{% extends "weaver/doc_page.jinja" %}` but the Jinja loader search path is
  `templates/weaver`, so the correct path is just `{% extends "doc_page.jinja" %}`.
  Evidence: Generator raised `TemplateNotFound: weaver/doc_page.jinja` on first run.
  Impact: Fixed with sed; all page templates updated before committing.

## Decision log

- Decision: Extend `SubSiteHomePageBuilder` with optional `nav_links` /
  `parent_link` kwargs rather than embedding them in the YAML
  `homepage.context` dict. Rationale: Keeps the YAML clean; avoids duplicating
  structured nav data in the freeform context block; consistent with how
  `ContentPageGenerator` works. The change is additive and backward-compatible
  (both new kwargs default to `None`/`[]`). Date/Author: 2026-05-05 (plan phase)

- Decision: Update weaver and netsuke `nav_links` in `pages.yaml` to absolute
  paths before wiring up content pages. Rationale:
  `ContentPageGenerator._mark_current_nav()` computes `target_href` as an
  absolute path (`/site/slug/`). Relative hrefs in `nav_links` would never
  match, silently breaking active-link highlighting on every generated page.
  Absolute paths also work correctly from shared_content_page.jinja.
  Date/Author: 2026-05-05 (plan phase)

- Decision: Approach content-page migration as "lift HTML into template, wrap
  in base template extends, delete source file". No content changes are
  permitted during migration. Rationale: Visual fidelity is a hard constraint;
  mixing migration and design changes introduces unnecessary risk and
  complicates validation. Date/Author: 2026-05-05 (plan phase)

## Outcomes & retrospective

(to be completed)

## Context and orientation

### Repository layout (relevant paths)

```plaintext
config/pages.yaml                   — central site configuration (YAML)
df12_pages/                         — Python package that drives the build
  cli.py                            — `pages generate` entrypoint
  subsite_homepage.py               — SubSiteHomePageBuilder class
  content_page.py                   — ContentPageGenerator class
  shared_content.py                 — SharedContentGenerator class
  config/
    models.py                       — typed dataclasses for config
    loader.py                       — YAML → dataclass loader
templates/
  mxd/
    doc_page.jinja                  — base template for mxd content pages
    shared_content_page.jinja       — shared chrome for terms/privacy/CoC
    pages/                          — 9 existing content page templates
  netsuke/
    shared_content_page.jinja       — shared chrome (no other templates yet)
  weaver/
    shared_content_page.jinja       — shared chrome (no other templates yet)
public/
  mxd/                              — output dir; index.html still hard-coded
  netsuke/                          — output dir; all content pages hard-coded
  weaver/                           — output dir; all content pages hard-coded
```

### How the build pipeline works

`pages generate --site mxd` calls `_generate_subsite(site_config, subsite)` in
`cli.py`. That function:

1. Renders doc pages (from `subsite.pages` — empty for all three sites
   currently).
2. Renders the homepage if `subsite.homepage` is set (currently `None` for all
   three).
3. Renders shared content (terms-of-use, privacy-policy, code-of-conduct) via
   `SharedContentGenerator`, using `templates/{site}/shared_content_page.jinja`.
4. Renders content pages (from `subsite.content_pages`) via
   `ContentPageGenerator`, using a per-page template that extends
   `templates/{site}/doc_page.jinja`.
5. Copies static assets from `subsite.static_assets_dir` (not used by any of
   the three sites currently).

### How homepages work

`SubSiteHomePageBuilder` loads `templates/{site}/home_page.jinja` and renders
it with a `homepage` dict (built from the YAML `homepage.context` block plus
`title`) and a `generated_at` timestamp. It does **not** currently receive
`nav_links` or `parent_link`. Both must be threaded through so templates can
render navigation.

### How content pages work

`ContentPageGenerator` loads a template identified by
`ContentPageConfig.template` (relative to `templates/{site}/`), renders it with
`nav_links`, `parent_link`, `stylesheet`, and `generated_at`, and writes to
`{output_dir}/{output_slug}/index.html`. For mxd, every content page template
extends `doc_page.jinja`, filling named blocks (`page_title`, `hero`,
`route_map`, `content`, `footer_cta`).

### Nav-link active marking

`_mark_current_nav()` sets `current: true` on the nav link whose `href` matches
`{base_path}{output_slug}/`. This requires nav links to use absolute paths (e.g.
 `/weaver/why-weaver/`). Weaver and netsuke currently use relative paths (
`../why-weaver/`), which will not match and must be corrected.

### Template patterns in use

mxd `doc_page.jinja` is the reference pattern:

- A standalone `<!DOCTYPE html>` document.
- CDN stylesheet references use absolute paths (`/mxd/assets/...`).
- Named blocks: `page_title`, `hero`, `route_map`, `content`, `footer_cta`.
- Navigation rendered from injected `nav_links` and `parent_link` context
  variables.

Each site's `doc_page.jinja` will follow the same block structure, adapted to
the site's own visual design.

### Currently hard-coded pages per site

**mxd** (1 page):

- `public/mxd/index.html` — homepage

**weaver** (14 pages):

- `public/weaver/index.html`
- `public/weaver/why-weaver/index.html`
- `public/weaver/how-it-works/index.html`
- `public/weaver/commands/index.html`
- `public/weaver/commands/act/index.html`
- `public/weaver/commands/observe/index.html`
- `public/weaver/commands/verify/index.html`
- `public/weaver/safety/index.html`
- `public/weaver/sempai/index.html`
- `public/weaver/jacquard/index.html`
- `public/weaver/install/index.html`
- `public/weaver/roadmap/index.html`
- `public/weaver/docs/index.html`
- `public/weaver/design-language/index.html`

**netsuke** (20 pages):

- `public/netsuke/index.html`
- `public/netsuke/blog/index.html`
- `public/netsuke/contributing/index.html`
- `public/netsuke/design/index.html`
- `public/netsuke/docs/index.html`
- `public/netsuke/docs/cli-security-and-configuration/index.html`
- `public/netsuke/docs/getting-started/index.html`
- `public/netsuke/docs/manifest-reference/index.html`
- `public/netsuke/docs/rules-and-targets/index.html`
- `public/netsuke/docs/templating-and-standard-library/index.html`
- `public/netsuke/examples/index.html`
- `public/netsuke/examples/basic-c-application/index.html`
- `public/netsuke/examples/batch-photo-processing/index.html`
- `public/netsuke/examples/hello-world/index.html`
- `public/netsuke/examples/multi-format-documentation/index.html`
- `public/netsuke/examples/static-site-pipeline/index.html`
- `public/netsuke/examples/visual-design-assets/index.html`
- `public/netsuke/guides/index.html`
- `public/netsuke/install/index.html`
- `public/netsuke/icon-replacements/index.html`

## Plan of work

### Stage 1 — mxd homepage

**Step 1.1 — Extend `SubSiteHomePageBuilder`.**

In `df12_pages/subsite_homepage.py`, add two optional kwargs to
`SubSiteHomePageBuilder.__init__`:

```python
nav_links: list[NavLinkConfig] | None = None,
parent_link: NavLinkConfig | None = None,
```

Store them as instance attributes. In `run()`, include them in the render
context:

```python
context = {
    "homepage": {...},
    "generated_at": ...,
    "nav_links": [dc.asdict(l) for l in (self.nav_links or [])],
    "parent_link": dc.asdict(self.parent_link) if self.parent_link else None,
}
```

Import `dataclasses as dc` if not already present.

**Step 1.2 — Update `cli.py`.**

In `_generate_subsite`, update the homepage builder call:

```python
hp_path = SubSiteHomePageBuilder(
    subsite.homepage,
    templates_dir=templates_dir,
    nav_links=subsite.nav_links,
    parent_link=subsite.parent_link,
).run()
```

**Step 1.3 — Create `templates/mxd/home_page.jinja`.**

Lift the content from `public/mxd/index.html` verbatim into a Jinja template.
Replace the hardcoded `<head>`, nav `<header>`, and `<footer>` with the
equivalents from `doc_page.jinja` (they are identical). Render nav links and
the parent link from the injected `nav_links` / `parent_link` context
variables, matching the loop already in `doc_page.jinja`:

```jinja
{% for link in nav_links %}<a href="{{ link.href }}"{% if link.href == "./" %} aria-current="page"{% endif %}>{{ link.label }}</a>{% endfor %}
```

The `<main>` body content (all five content sections plus footer-CTA) is unique
to the homepage and is pasted verbatim. Change asset references from relative (
`assets/...`) to absolute (`/mxd/assets/...`) to be consistent with the
generated content pages.

**Step 1.4 — Add homepage config to `config/pages.yaml`.**

Under `sites.mxd`, add:

```yaml
homepage:
  title: "Home — mxd"
```

No additional context keys are needed; the template content is static.

**Step 1.5 — Regenerate and validate.**

```bash
pages generate --site mxd
```

Use Playwright to navigate to `http://127.0.0.1:8080/mxd/` and take a
screenshot. Compare with the reference screenshot captured during planning. Use
`css-view` to diff the computed styles of key structural elements (hero, nav,
footer) between the hard-coded page and the newly generated page — differences
should be zero.

**Step 1.6 — Delete the hard-coded file.**

```bash
rm public/mxd/index.html
```

Regenerate and re-verify.

**Step 1.7 — Gate commit.**

```bash
make fmt check-fmt typecheck lint test
```

Commit with message `feat: template mxd homepage`.

______________________________________________________________________

### Stage 2 — weaver (14 pages)

**Step 2.1 — Update weaver nav links to absolute paths.**

In `config/pages.yaml`, under `sites.weaver.nav_links`, change all hrefs from
relative (`../`) to absolute (`/weaver/`):

```yaml
nav_links:
  - label: Home
    href: /weaver/
  - label: Philosophy
    href: /weaver/why-weaver/
  - label: Architecture
    href: /weaver/how-it-works/
  - label: Commands
    href: /weaver/commands/
  - label: Safety
    href: /weaver/safety/
  - label: Sempai Engine
    href: /weaver/sempai/
  - label: Jacquard
    href: /weaver/jacquard/
  - label: Install
    href: /weaver/install/
  - label: Docs
    href: /weaver/docs/
  - label: Roadmap
    href: /weaver/roadmap/
```

Regenerate shared content to confirm the existing shared_content_page.jinja
still produces correct output:

```bash
pages generate --site weaver
```

Spot-check `public/weaver/terms-of-use/index.html` — nav link hrefs should now
be absolute.

**Step 2.2 — Create `templates/weaver/doc_page.jinja`.**

This is the base template for all weaver content pages. It contains:

- Full `<head>` with Font Awesome CDN, Tailwind CDN + config block, Google
  Fonts link, and
  `<link rel="stylesheet" href="/weaver/assets/styles/weaver-site.css">`.
- The sidebar `<aside>` with the WEAVER brand, nav links rendered from
  `nav_links` context (marking the active link), and the back-link footer.
- A `<main>` element with a `{% block content %}{% endblock %}` for
  page-specific body.
- The weaver `<footer>` block (shared by all content pages).
- The inline smooth-scroll `<script>` and
  `<script src="/weaver/assets/js/mobile-nav.js">`.

The sidebar nav renders the injected `nav_links` list, setting the active state
class on the link whose `href` matches the current page. The `parent_link` is
rendered in the sidebar footer area (`← Back to df12 Productions`).

Lift this structure directly from `public/weaver/why-weaver/index.html`, which
is a representative content page. Change all relative asset paths (
`../assets/`) to absolute (`/weaver/assets/`).

Named blocks: `page_title` (for `<title>`), `content` (page body inside main).

**Step 2.3 — Create `templates/weaver/home_page.jinja`.**

Lift from `public/weaver/index.html`. Structure: full `<head>` (same as
doc_page), sidebar nav with Home marked active, full hero + value-props +
commands preview + Sempai + links-grid sections, and the weaver footer. Change
relative asset refs to absolute.

This is a standalone template (does not extend `doc_page.jinja`) because the
homepage has structural differences in the sidebar footer and hero layout.

**Step 2.4 — Create 13 content page templates.**

Create `templates/weaver/pages/{slug}.jinja` for each content page, extending
`doc_page.jinja`. Each template fills at minimum the `page_title` and `content`
blocks with content lifted verbatim from the corresponding
`public/weaver/{slug}/index.html`. Change relative asset refs (`../assets/`) to
absolute (`/weaver/assets/`).

Pages and their template paths:

- `why-weaver` → `pages/why-weaver.jinja`
- `how-it-works` → `pages/how-it-works.jinja`
- `commands` → `pages/commands.jinja`
- `commands/act` → `pages/commands-act.jinja`
- `commands/observe` → `pages/commands-observe.jinja`
- `commands/verify` → `pages/commands-verify.jinja`
- `safety` → `pages/safety.jinja`
- `sempai` → `pages/sempai.jinja`
- `jacquard` → `pages/jacquard.jinja`
- `install` → `pages/install.jinja`
- `roadmap` → `pages/roadmap.jinja`
- `docs` → `pages/docs.jinja`
- `design-language` → `pages/design-language.jinja`

Note: the nested sub-command pages (`commands/act` etc.) use flat template
filenames (`commands-act.jinja`) to avoid creating sub-directories in the
`pages/` template folder. The `output_slug` value in the YAML (`commands/act`)
controls the output path; the template filename is independent.

**Step 2.5 — Add homepage and content_pages config to `sites.weaver`.**

In `config/pages.yaml`:

```yaml
sites:
  weaver:
    ...
    homepage:
      title: "Weaver — AI Codebase Tooling"
    content_pages:
      - key: why-weaver
        label: Philosophy
        template: pages/why-weaver.jinja
        output_slug: why-weaver
      - key: how-it-works
        label: Architecture
        template: pages/how-it-works.jinja
        output_slug: how-it-works
      - key: commands
        label: Commands
        template: pages/commands.jinja
        output_slug: commands
      - key: commands-act
        label: Act
        template: pages/commands-act.jinja
        output_slug: commands/act
      - key: commands-observe
        label: Observe
        template: pages/commands-observe.jinja
        output_slug: commands/observe
      - key: commands-verify
        label: Verify
        template: pages/commands-verify.jinja
        output_slug: commands/verify
      - key: safety
        label: Safety
        template: pages/safety.jinja
        output_slug: safety
      - key: sempai
        label: Sempai Engine
        template: pages/sempai.jinja
        output_slug: sempai
      - key: jacquard
        label: Jacquard
        template: pages/jacquard.jinja
        output_slug: jacquard
      - key: install
        label: Install
        template: pages/install.jinja
        output_slug: install
      - key: roadmap
        label: Roadmap
        template: pages/roadmap.jinja
        output_slug: roadmap
      - key: docs
        label: Docs
        template: pages/docs.jinja
        output_slug: docs
      - key: design-language
        label: Design Language
        template: pages/design-language.jinja
        output_slug: design-language
```

**Step 2.6 — Regenerate and validate.**

```bash
pages generate --site weaver
```

Use Playwright to visit at least: `/weaver/`, `/weaver/why-weaver/`,
`/weaver/commands/`, `/weaver/commands/act/`, `/weaver/safety/`. Take
screenshots. Use `css-view` to diff the sidebar nav structure between the
hard-coded and generated versions of `why-weaver` — expect no differences.

**Step 2.7 — Delete the 14 hard-coded files.**

```bash
rm public/weaver/index.html
rm public/weaver/why-weaver/index.html
rm public/weaver/how-it-works/index.html
rm public/weaver/commands/index.html
rm public/weaver/commands/act/index.html
rm public/weaver/commands/observe/index.html
rm public/weaver/commands/verify/index.html
rm public/weaver/safety/index.html
rm public/weaver/sempai/index.html
rm public/weaver/jacquard/index.html
rm public/weaver/install/index.html
rm public/weaver/roadmap/index.html
rm public/weaver/docs/index.html
rm public/weaver/design-language/index.html
```

Regenerate and re-verify. Confirm the generated files match what was deleted.

**Step 2.8 — Gate commit.**

```bash
make fmt check-fmt typecheck lint test
```

Commit with message `feat: template weaver sub-site`.

______________________________________________________________________

### Stage 3 — netsuke (20 pages)

**Step 3.1 — Update netsuke nav links to absolute paths.**

In `config/pages.yaml`, under `sites.netsuke.nav_links`:

```yaml
nav_links:
  - label: Home
    href: /netsuke/
  - label: Docs
    href: /netsuke/docs/
  - label: Examples
    href: /netsuke/examples/
  - label: Guides
    href: /netsuke/guides/
  - label: Blog
    href: /netsuke/blog/
```

Regenerate and spot-check shared content.

**Step 3.2 — Create `templates/netsuke/doc_page.jinja`.**

Base template for netsuke content pages. Contains:

- `<head>` with Tailwind CDN, Iconify CDN, Google Fonts (Fraunces, JetBrains
  Mono, Source Sans 3), and
  `<link rel="stylesheet" href="/netsuke/assets/css/himotoshi.css">`.
- The fixed top `<nav>` with brand logo, desktop nav links from `nav_links`
  context (marking active), GitHub/install action buttons, and mobile menu.
- `<main>` with `{% block content %}{% endblock %}`.
- The netsuke `<footer>` shared by all content pages.
- `<script defer src="/netsuke/assets/js/mobile-nav.js">`.

Named blocks: `page_title`, `content`.

Lift from a representative content page (e.g.,
`public/netsuke/install/index.html`). Change relative asset refs to absolute (
`/netsuke/assets/...`).

**Step 3.3 — Create `templates/netsuke/home_page.jinja`.**

Lift from `public/netsuke/index.html`. This is a standalone template (does not
extend `doc_page.jinja`) because the homepage has a full-viewport hero with
background image and a significantly different structure from content pages.

Change all relative asset refs to absolute (`/netsuke/assets/...`). Note the
homepage includes `assets/js/tailwind-config.js` and Plotly CDN; preserve these
verbatim.

**Step 3.4 — Create 19 content page templates.**

Create `templates/netsuke/pages/{name}.jinja` for each content page. Nested
output slugs use flat template names with path segments in `output_slug`:

- `blog` → `pages/blog.jinja`
- `contributing` → `pages/contributing.jinja`
- `design` → `pages/design.jinja`
- `docs` → `pages/docs.jinja`
- `docs/cli-security-and-configuration` →
  `pages/docs-cli-security-and-configuration.jinja`
- `docs/getting-started` → `pages/docs-getting-started.jinja`
- `docs/manifest-reference` → `pages/docs-manifest-reference.jinja`
- `docs/rules-and-targets` → `pages/docs-rules-and-targets.jinja`
- `docs/templating-and-standard-library` →
  `pages/docs-templating-and-standard-library.jinja`
- `examples` → `pages/examples.jinja`
- `examples/basic-c-application` →
  `pages/examples-basic-c-application.jinja`
- `examples/batch-photo-processing` →
  `pages/examples-batch-photo-processing.jinja`
- `examples/hello-world` → `pages/examples-hello-world.jinja`
- `examples/multi-format-documentation` →
  `pages/examples-multi-format-documentation.jinja`
- `examples/static-site-pipeline` →
  `pages/examples-static-site-pipeline.jinja`
- `examples/visual-design-assets` →
  `pages/examples-visual-design-assets.jinja`
- `guides` → `pages/guides.jinja`
- `install` → `pages/install.jinja`
- `icon-replacements` → `pages/icon-replacements.jinja`

**Step 3.5 — Add homepage and content_pages config to `sites.netsuke`.**

Add a `homepage:` block (title only) and a full `content_pages:` list to
`sites.netsuke` in `config/pages.yaml`, following the same pattern as Stage 2.

**Step 3.6 — Regenerate and validate.**

```bash
pages generate --site netsuke
```

Playwright spot-check: `/netsuke/`, `/netsuke/install/`, `/netsuke/docs/`,
`/netsuke/docs/getting-started/`, `/netsuke/examples/hello-world/`,
`/netsuke/blog/`. Use `css-view` to diff the nav structure of the hard-coded
vs. generated `install` page.

**Step 3.7 — Delete 20 hard-coded HTML files.**

Delete every `public/netsuke/*/index.html` and `public/netsuke/index.html`
listed under "Currently hard-coded pages" above.

Regenerate and re-verify.

**Step 3.8 — Gate commit.**

```bash
make fmt check-fmt typecheck lint test
```

Commit with message `feat: template netsuke sub-site`.

## Concrete steps

All commands run from
`/data/leynos/Projects/df12-www.worktrees/templatize-sub-sites`.

### Stage 1 commands

```bash
# Edit df12_pages/subsite_homepage.py
# Edit df12_pages/cli.py
# Create templates/mxd/home_page.jinja
# Edit config/pages.yaml

pages generate --site mxd
# Verify http://127.0.0.1:8080/mxd/ with Playwright

rm public/mxd/index.html
pages generate --site mxd

make fmt
make check-fmt
make typecheck
make lint
make test
git add ...
git commit
```

### Stage 2 commands

```bash
# Edit config/pages.yaml (nav_links + homepage + content_pages for weaver)
# Create templates/weaver/doc_page.jinja
# Create templates/weaver/home_page.jinja
# Create templates/weaver/pages/*.jinja (13 files)

pages generate --site weaver
# Verify http://127.0.0.1:8080/weaver/ and spot-check pages with Playwright

rm public/weaver/index.html
rm public/weaver/why-weaver/index.html
# ... (all 14 files)
pages generate --site weaver

make fmt
make check-fmt
make typecheck
make lint
make test
git add ...
git commit
```

### Stage 3 commands

```bash
# Edit config/pages.yaml (nav_links + homepage + content_pages for netsuke)
# Create templates/netsuke/doc_page.jinja
# Create templates/netsuke/home_page.jinja
# Create templates/netsuke/pages/*.jinja (19 files)

pages generate --site netsuke
# Verify http://127.0.0.1:8080/netsuke/ and spot-check pages with Playwright

rm public/netsuke/index.html
rm public/netsuke/blog/index.html
# ... (all 20 files)
pages generate --site netsuke

make fmt
make check-fmt
make typecheck
make lint
make test
git add ...
git commit
```

## Validation and acceptance

### Per-stage acceptance criteria

**Stage 1 (mxd):**

- `pages generate --site mxd` exits 0 and prints `wrote public/mxd/index.html`.
- `http://127.0.0.1:8080/mxd/` renders identically to the reference screenshot
  (Playwright, viewport 1280×800).
- `css-view` diff of the `#hero-section` subtree shows zero differences between
  the hard-coded and generated page.
- `public/mxd/index.html` no longer exists in git.
- `make fmt check-fmt typecheck lint test` passes.

**Stage 2 (weaver):**

- `pages generate --site weaver` exits 0 and prints `wrote` lines for all 14
  non-shared pages.
- Playwright screenshots of `/weaver/`, `/weaver/commands/act/` match
  reference.
- No hard-coded `index.html` files remain in `public/weaver/` (confirmed by
  `git status` showing deletions).
- `make fmt check-fmt typecheck lint test` passes.

**Stage 3 (netsuke):**

- `pages generate --site netsuke` exits 0 and prints `wrote` lines for all 20
  non-shared pages.
- Playwright screenshots of `/netsuke/`, `/netsuke/docs/getting-started/`,
  `/netsuke/examples/hello-world/` match reference.
- No hard-coded `index.html` files remain in `public/netsuke/`.
- `make fmt check-fmt typecheck lint test` passes.

### Quality method

```bash
make fmt          # auto-format (Python)
make check-fmt    # assert clean format
make typecheck    # ty / mypy
make lint         # ruff / markdownlint
make test         # pytest (including any Playwright tests unless SKIP_PLAYWRIGHT=1)
```

Run each sequentially after all file changes within a stage are complete. Do
not proceed to the next stage if any command fails.

## Idempotence and recovery

`pages generate --site {site}` is idempotent — re-running it overwrites the
output files without side effects. If a generation step fails partway, delete
any partial output under `public/{site}/` and re-run.

Deleting hard-coded files is a one-way operation. Before deleting, confirm the
generated output is present and correct. Git history preserves the originals;
run `git show HEAD:{path}` to recover any deleted file.

## Artifacts and notes

Reference Playwright screenshots captured during planning are stored at:

```plaintext
/tmp/.playwright-mcp/mxd-homepage.png
/tmp/.playwright-mcp/weaver-homepage.png
/tmp/.playwright-mcp/netsuke-homepage.png
```

These are ephemeral (tmp); re-capture from the dev server if needed.

## Interfaces and dependencies

### Modified Python interface

`df12_pages.subsite_homepage.SubSiteHomePageBuilder.__init__` gains two new
optional parameters:

```python
def __init__(
    self,
    config: SubSiteHomepageConfig,
    *,
    templates_dir: Path | None = None,
    nav_links: list[NavLinkConfig] | None = None,
    parent_link: NavLinkConfig | None = None,
) -> None: ...
```

The render context in `run()` gains:

```python
"nav_links": [dc.asdict(link) for link in (self.nav_links or [])],
"parent_link": dc.asdict(self.parent_link) if self.parent_link else None,
```

All callers in `cli.py` pass `nav_links=subsite.nav_links` and
`parent_link=subsite.parent_link`.

### New template files (35 files total)

```plaintext
templates/mxd/home_page.jinja                         (1)
templates/weaver/doc_page.jinja                       (1)
templates/weaver/home_page.jinja                      (1)
templates/weaver/pages/why-weaver.jinja               (1)
templates/weaver/pages/how-it-works.jinja             (1)
templates/weaver/pages/commands.jinja                 (1)
templates/weaver/pages/commands-act.jinja             (1)
templates/weaver/pages/commands-observe.jinja         (1)
templates/weaver/pages/commands-verify.jinja          (1)
templates/weaver/pages/safety.jinja                   (1)
templates/weaver/pages/sempai.jinja                   (1)
templates/weaver/pages/jacquard.jinja                 (1)
templates/weaver/pages/install.jinja                  (1)
templates/weaver/pages/roadmap.jinja                  (1)
templates/weaver/pages/docs.jinja                     (1)
templates/weaver/pages/design-language.jinja          (1)
templates/netsuke/doc_page.jinja                      (1)
templates/netsuke/home_page.jinja                     (1)
templates/netsuke/pages/blog.jinja                    (1)
templates/netsuke/pages/contributing.jinja            (1)
templates/netsuke/pages/design.jinja                  (1)
templates/netsuke/pages/docs.jinja                    (1)
templates/netsuke/pages/docs-cli-security-...jinja    (1)
templates/netsuke/pages/docs-getting-started.jinja    (1)
templates/netsuke/pages/docs-manifest-reference.jinja (1)
templates/netsuke/pages/docs-rules-and-targets.jinja  (1)
templates/netsuke/pages/docs-templating-....jinja     (1)
templates/netsuke/pages/examples.jinja                (1)
templates/netsuke/pages/examples-basic-c-....jinja    (1)
templates/netsuke/pages/examples-batch-photo-...jinja (1)
templates/netsuke/pages/examples-hello-world.jinja    (1)
templates/netsuke/pages/examples-multi-....jinja      (1)
templates/netsuke/pages/examples-static-....jinja     (1)
templates/netsuke/pages/examples-visual-....jinja     (1)
templates/netsuke/pages/guides.jinja                  (1)
templates/netsuke/pages/install.jinja                 (1)
templates/netsuke/pages/icon-replacements.jinja       (1)
```

(37 new template files in total; 35 listed above plus 2 netsuke — guides and
icon-replacements are included in the count.)
