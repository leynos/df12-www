# Multi-Site Generation for df12_pages

## Context

df12_pages currently generates a single flat site under one domain: the
df12.studio marketing homepage, about page, docs index, and per-project
documentation bundles. Three product sub-sites (weaver, netsuke, mxd) exist as
hand-built static HTML in separate repos, each with a distinct visual identity,
navigation pattern, and CSS architecture. They already contain duplicated
shared copy (terms of use, privacy policy) wrapped in each site's chrome.

The goal is to extend df12_pages to generate all four sites from a single
`pages generate --all-sites` invocation: the main df12 site at `/`, plus
sub-sites at `/weaver/`, `/netsuke/`, `/mxd/`. Each sub-site keeps its own
templates, fonts, colour palette, and CSS. Shared copy (terms, privacy, code of
conduct) comes from a single markdown source but renders through each site's
template wrapper.

### Design decisions (settled)

- **Shared copy**: Generate per sub-site with that site's
  theme (Option B)
- **Deployment**: Path-prefix (single bucket, single domain)
- **CSS**: Separate entry point per sub-site
- **Cross-linking**: Sub-site headers carry "About df12"
  link to `/`; main homepage panels link to sub-sites
- **Generation**: Full generation — df12_pages generates
  every page of every sub-site from per-site Jinja template sets + config

______________________________________________________________________

## Architecture

### Key insight: templates_dir is already the right seam

Every existing builder class (`PageContentGenerator`, `HomePageBuilder`,
`AboutPageBuilder`, `DocsIndexBuilder`) already accepts a `templates_dir`
parameter. Each resolves templates by name (e.g. `doc_page.jinja`) relative to
that directory. Sub-site generation composes these same builders with a
different `templates_dir` per site. No builder internals change.

### Homepage config problem

The existing `HomepageConfig` is df12-specific (hero with brand lockup, systems
cards, worlds cards). Sub-site homepages have fundamentally different content:
mxd has protocol hex displays and architecture diagrams; weaver has a sidebar
layout with CLI install commands; netsuke has benchmark charts. Creating
per-site dataclasses would mean dozens of types consumed by only one template
each.

**Solution**: A new `SubSiteHomepageConfig` carries typed structural fields
(`output`, `title`) plus a freeform `context: dict[str, Any]` holding the raw
YAML payload. Each sub-site's `home_page.jinja` accesses what it needs from the
context dict. Jinja handles dict attribute access transparently.

______________________________________________________________________

## Implementation

### Phase 1 — Config models

**File**: `df12_pages/config/models.py`

Add three new dataclasses:

```python
@dc.dataclass(slots=True)
class SharedContentConfig:
    """Shared-copy page rendered into each sub-site."""
    key: str           # "terms-of-use", "privacy-policy"
    label: str         # "Terms of Use"
    source: str        # local path or URL to markdown
    output_slug: str   # "terms-of-use" → terms-of-use/index.html

@dc.dataclass(slots=True)
class SubSiteHomepageConfig:
    """Homepage config with freeform template context."""
    output: Path
    title: str
    context: dict[str, typ.Any]  # raw YAML for template

@dc.dataclass(slots=True)
class SubSiteConfig:
    """Self-contained sub-site with own templates and CSS."""
    key: str                            # "weaver"
    output_dir: Path                    # Path("public/weaver")
    templates_dir: Path                 # Path("templates/weaver")
    stylesheet: str                     # "assets/weaver.css"
    base_path: str                      # "/weaver/"
    theme: ThemeConfig
    pages: dict[str, PageConfig]
    homepage: SubSiteHomepageConfig | None
    about: AboutPageConfig | None
    docs_index_output: Path | None
    shared_content_refs: list[str]      # keys into shared
    nav_links: list[NavLinkConfig]      # sub-site nav
    parent_link: NavLinkConfig | None   # "About df12"
    static_assets_dir: Path | None      # copied to output
```

Extend `SiteConfig`:

```python
@dc.dataclass(slots=True)
class SiteConfig:
    pages: dict[str, PageConfig]
    # ... existing fields ...
    sites: dict[str, SubSiteConfig] = dc.field(
        default_factory=dict,
    )
    shared_content: dict[str, SharedContentConfig] = dc.field(
        default_factory=dict,
    )
```

### Phase 2 — Config loader

**File**: `df12_pages/config/loader.py`

- Add `_build_shared_content_map()`: parses the top-level
  `shared_content` YAML block into `dict[str, SharedContentConfig]`
- Add `_build_subsite_config()`: parses each entry under
  `sites`, reusing `_build_page_config()` for sub-site pages and
  `_merge_theme()` for theme inheritance
- Modify `load_site_config()`: after existing parsing, parse
  `shared_content` and `sites` blocks, attach to `SiteConfig`
- **Backward compat**: if `sites` key absent,
  `SiteConfig.sites` is an empty dict. Existing behaviour unchanged.

### Phase 3 — SharedContentGenerator

**New file**: `df12_pages/shared_content.py`

Follows the `HomePageBuilder` pattern:

```python
class SharedContentGenerator:
    def __init__(
        self,
        shared_config: SharedContentConfig,
        output_dir: Path,
        *,
        templates_dir: Path | None = None,
        template_name: str = "shared_content_page.jinja",
    ) -> None: ...

    def run(self) -> Path:
        """Fetch/read markdown, render HTML, wrap, write."""
```

- `source` can be a local file path or URL (detect `://`)
- Markdown rendered with `fenced_code`, `tables`,
  `sane_lists` extensions
- Output written to `{output_dir}/{output_slug}/index.html`
  (clean URLs matching existing sub-site patterns)
- Template receives `title`, `body_html`, `generated_at`,
  `nav_links`, `parent_link`

### Phase 4 — Sub-site homepage builder

**New file**: `df12_pages/subsite_homepage.py`

```python
class SubSiteHomePageBuilder:
    def __init__(
        self,
        config: SubSiteHomepageConfig,
        *,
        templates_dir: Path | None = None,
    ) -> None: ...

    def run(self) -> Path:
        """Render sub-site homepage from freeform context."""
```

- Creates Jinja env from `templates_dir`
- Loads `home_page.jinja` (same name convention)
- Passes `config.context` plus `generated_at` to template
- Each sub-site's `home_page.jinja` is completely bespoke

### Phase 5 — CLI orchestration

**File**: `df12_pages/cli.py`

Add `--site` and `--all-sites` parameters to `generate`:

```text
pages generate                        # main only (compat)
pages generate --all-sites            # main + all sub-sites
pages generate --site weaver          # one sub-site
pages generate --site weaver --page wireframe
```

Extract current `generate` body into `_generate_main_site()`. Add
`_generate_subsite()`:

```python
def _generate_subsite(
    site_config: SiteConfig,
    subsite: SubSiteConfig,
    ...,
) -> None:
    templates_dir = subsite.templates_dir

    # 1. Doc pages (reuses PageContentGenerator)
    for page_config in target_pages:
        generator = PageContentGenerator(
            page_config,
            templates_dir=templates_dir,
        )
        written = generator.run()

    # 2. Docs index (reuses DocsIndexBuilder)
    if subsite.pages and subsite.docs_index_output:
        scoped = SiteConfig(
            pages=subsite.pages,
            docs_index_output=subsite.docs_index_output,
            theme=subsite.theme,
        )
        DocsIndexBuilder(
            scoped,
            templates_dir=templates_dir,
        ).run()

    # 3. Homepage (SubSiteHomePageBuilder)
    if subsite.homepage:
        SubSiteHomePageBuilder(
            subsite.homepage,
            templates_dir=templates_dir,
        ).run()

    # 4. About page (reuses AboutPageBuilder)
    if subsite.about:
        AboutPageBuilder(
            subsite.about,
            templates_dir=templates_dir,
        ).run()

    # 5. Shared content per referenced key
    for ref_key in subsite.shared_content_refs:
        sc = site_config.shared_content[ref_key]
        SharedContentGenerator(
            sc,
            subsite.output_dir,
            templates_dir=templates_dir,
        ).run()
```

### Phase 6 — Per-site templates

Create template directories for each sub-site:

```text
templates/
  weaver/
    home_page.jinja               # sidebar layout
    doc_page.jinja                # weaver doc sections
    docs_index.jinja              # weaver docs landing
    shared_content_page.jinja     # weaver legal wrapper
    partials/
      site_macros.jinja           # sidebar nav, footer
  netsuke/
    home_page.jinja               # fixed top nav
    doc_page.jinja
    docs_index.jinja
    shared_content_page.jinja
    partials/
      site_macros.jinja
  mxd/
    home_page.jinja               # top nav with logo
    doc_page.jinja
    docs_index.jinja
    shared_content_page.jinja
    partials/
      site_macros.jinja
```

Main-site templates (under `df12_pages/templates/`) stay untouched. Add only
`shared_content_page.jinja` for the main site.

Templates reference their sub-site's stylesheet via `{{ stylesheet }}`, not
hard-coded `assets/site.css`. The sub-site config's `stylesheet` field flows
through the template context.

### Phase 7 — CSS entry points

```text
src/styles/
  site.css       # existing main site (unchanged)
  weaver.css     # Tailwind + DaisyUI weaver theme
  netsuke.css    # Fraunces + custom theme tokens
  mxd.css        # JetBrains Mono + Moroccan palette
```

Each compiles independently to its sub-site's output:

```text
public/weaver/assets/weaver.css
public/netsuke/assets/netsuke.css
public/mxd/assets/mxd.css
```

Build scripts added to `package.json` (or Makefile targets).

### Phase 8 — Static asset handling

Sub-sites need their own assets (logos, images, fonts). The `static_assets_dir`
field on `SubSiteConfig` points to a directory that gets copied to
`{output_dir}/assets/` during generation. This could be handled by a simple
`shutil.copytree` call in `_generate_subsite()`, or delegated to the
build/deploy pipeline.

______________________________________________________________________

## YAML config shape (target)

```yaml
defaults:
  # ... existing defaults, unchanged ...

shared_content:
  terms-of-use:
    label: "Terms of Use"
    source: config/shared/terms-of-use.md
    output_slug: terms-of-use
  privacy-policy:
    label: "Privacy Policy"
    source: config/shared/privacy-policy.md
    output_slug: privacy-policy
  code-of-conduct:
    label: "Code of Conduct"
    source: config/shared/code-of-conduct.md
    output_slug: code-of-conduct

homepage:
  # ... existing main site homepage, unchanged ...

about:
  # ... existing about page, unchanged ...

pages:
  # ... existing main site doc pages, unchanged ...

sites:
  weaver:
    output_dir: public/weaver
    templates_dir: templates/weaver
    stylesheet: assets/weaver.css
    base_path: /weaver/
    static_assets_dir: templates/weaver/static
    theme:
      site_name: Weaver
      hero_eyebrow: Weaver
      hero_tagline: CLI tooling for code-aware agents
    parent_link:
      label: About df12
      href: /about.html
    nav_links:
      - label: Home
        href: ./
      - label: Docs
        href: docs/
      # ...
    shared_content:
      - terms-of-use
      - privacy-policy
      - code-of-conduct
    homepage:
      output: public/weaver/index.html
      title: "Weaver — CLI tooling"
      context:
        hero:
          title_line1: "CLI tooling for"
          title_line2: "code-aware"
          title_accent: "agents."
          description: >-
            Weaver connects AI agents
            to a real codebase...
          install_command: "cargo install weaver"
        # ... more sections ...
    pages: {}

  netsuke:
    output_dir: public/netsuke
    templates_dir: templates/netsuke
    stylesheet: assets/netsuke.css
    base_path: /netsuke/
    # ...

  mxd:
    output_dir: public/mxd
    templates_dir: templates/mxd
    stylesheet: assets/mxd.css
    base_path: /mxd/
    # ...
```

______________________________________________________________________

## What stays the same (no source changes)

| File                              | Why unchanged                  |
| --------------------------------- | ------------------------------ |
| `generator/page_generator.py`     | `templates_dir` param exists   |
| `homepage.py` / `HomePageBuilder` | `templates_dir` param exists   |
| `about_page.py`                   | `templates_dir` param exists   |
| `docs_index.py`                   | `templates_dir` param exists   |
| `generator/renderer.py`           | Theme-agnostic rendering       |
| `generator/link_rewriter.py`      | Template-independent           |
| `generator/models.py`             | `SectionModel` shared          |
| `markdown_parser.py`              | Pure parsing, no site logic    |
| `releases.py`                     | Site-independent API client    |
| `bump.py`                         | Site-independent metadata      |
| `config/helpers.py`               | Merge helpers reused           |
| `config/homepage.py`              | Still used for main site       |
| `config/about.py`                 | Reused for sub-sites           |
| Existing main-site templates      | Sub-sites use own dirs         |
| Existing `config/pages.yaml`      | All existing keys remain valid |

______________________________________________________________________

## Files to create or modify

| File                              | Action | Summary                  |
| --------------------------------- | ------ | ------------------------ |
| `df12_pages/config/models.py`     | Modify | Add 3 dataclasses        |
| `df12_pages/config/loader.py`     | Modify | Parse sites + shared     |
| `df12_pages/cli.py`               | Modify | `--site`/`--all-sites`   |
| `df12_pages/shared_content.py`    | Create | SharedContentGenerator   |
| `df12_pages/subsite_homepage.py`  | Create | SubSiteHomePageBuilder   |
| `df12_pages/templates/*.jinja`    | Create | Main shared content wrap |
| `templates/weaver/**`             | Create | Weaver template set      |
| `templates/netsuke/**`            | Create | Netsuke template set     |
| `templates/mxd/**`                | Create | Mxd template set         |
| `src/styles/weaver.css`           | Create | Weaver Tailwind entry    |
| `src/styles/netsuke.css`          | Create | Netsuke Tailwind entry   |
| `src/styles/mxd.css`              | Create | Mxd Tailwind entry       |
| `config/shared/terms-of-use.md`   | Create | Single source terms      |
| `config/shared/privacy-policy.md` | Create | Single source privacy    |
| `config/pages.yaml`               | Modify | Add shared + sites       |

______________________________________________________________________

## Implementation order

1. ~~**Models + loader** (Phase 1-2)~~ — **DONE** (`05b2268`)
2. ~~**SharedContentGenerator** (Phase 3)~~ — **DONE**
3. ~~**SubSiteHomePageBuilder** (Phase 4)~~ — **DONE**
4. ~~**CLI orchestration** (Phase 5)~~ — **DONE**
5. ~~**Main-site shared content template**~~ — **DONE**
6. ~~**All three sub-sites** (mxd, netsuke, weaver)~~ —
   **DONE**: shared content templates, YAML config, static assets copied,
   `pages generate --all-sites` verified
7. ~~**Additional session fixes**~~ — **DONE**:
   - Netsuke blog filter controls wired up as JS buttons (`e372a2d`)
   - Batch inline review fixes applied (`8e5571a`)
   - Netsuke blog missing Tailwind CDN + config restored (`14d96e7`)
   - mxd `src/styles/mxd.css` `@source` directives added so Tailwind v4
     oxide engine scans `.jinja` templates for arbitrary-value classes
     like `bg-[#12121f]` (`4cd73b5`)

______________________________________________________________________

## Verification

1. `pages generate` with existing config — must produce
   identical output (backward compat)
2. `pages generate --all-sites` — generates main site plus
   all sub-sites
3. `pages generate --site mxd` — generates only mxd under
   `public/mxd/`
4. Shared content pages render with correct site chrome
   (inspect HTML for site-specific nav, footer, CSS link)
5. Cross-links work: sub-site "About df12" links to
   `/about.html`; main homepage links to `/weaver/` etc.
6. Each sub-site's CSS compiles independently and is
   referenced correctly in generated HTML
7. Existing tests pass without modification.
