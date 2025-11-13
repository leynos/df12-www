# df12 Pages Application Design

This living document captures the architectural conventions for the df12
Pages generator, with a focus on how we talk to upstream services and how we
test those integrations reliably.

## GitHub API Access

### Client Library

- We use [`github3.py`](https://github3py.readthedocs.io/) for **all** GitHub
  interactions. Direct `requests` calls to `api.github.com` are not permitted.
- Instantiate a single `github3.GitHub` client per generator instance and reuse
  it across calls. This keeps connection pooling efficient and simplifies
  mocking.
- Authentication tokens:
  - Prefer the `GITHUB_TOKEN` environment variable. Fall back to `GH_TOKEN`.
  - Anonymous requests are allowed when neither variable is present, but code
    must handle rate‑limit or auth failures gracefully.
- Handle `github3` exceptions explicitly. Any `GitHubException` should be
  caught and translated into a soft failure (e.g., returning `None`) so we can
  continue rendering docs without hard crashing.

### Commit Metadata Lookup

When a documentation page does not have a release tag, we fall back to the
timestamp of the most recent commit touching the source Markdown path:

1. Split `owner/repo` from the page config.
2. Use `repository = github.repository(owner, name)`.
3. Call `repository.commits(path=..., sha=branch)` and grab the first result.
4. Prefer the `author.date`, then `committer.date`, normalizing to UTC.
5. Flow the resulting `datetime` into the rendered “Updated …” badge.

This approach keeps the generated HTML stable when the Markdown file hasn’t
changed, eliminating churn caused by build timestamps.

## Testing Strategy

### Unit Tests (pytest + pytest-mock)

- Use `pytest-mock` to patch `github3.GitHub` in place. Provide a fake client
  whose `repository().commits()` method returns lightweight objects (e.g.
  `SimpleNamespace`) with `commit.author.date` attributes.
- Drive scenarios by mutating the mocked commit date and asserting that the
  rendered BeautifulSoup tree reflects the expected “Updated …” string.
- Avoid touching the network entirely. All unit tests should run offline.

### Behaviour Tests (pytest-bdd + Betamax)

- For end-to-end coverage, continue to wrap `requests.Session` with Betamax
  (see `tests/bdd/`), using recorded cassettes checked into
  `tests/cassettes/`.
- Behaviour tests exercise the full CLI paths (e.g., rendering docs for a real
  repo + tag). Betamax ensures deterministic HTTP interactions without hitting
  GitHub during CI.
- The same Betamax instrumentation is reused for release metadata lookups, so
  future GitHub features should piggyback on that recording infrastructure.

### Test Matrix Summary

| Layer                | Tooling                        | Purpose                                      |
|----------------------|--------------------------------|----------------------------------------------|
| Unit                 | `pytest`, `pytest-mock`        | Fast validation of commit-date logic         |
| Behaviour / BDD      | `pytest-bdd`, `Betamax`        | Full pipeline with recorded HTTP responses   |

Following these patterns keeps our GitHub integration robust while preventing
flaky network-dependent tests.

## Pages Generation Strategy

1. **Repositories as the Source of Truth**
   - Each documentation bundle points at a GitHub repository (`repo`), a branch
     (default `main`), and a Markdown entrypoint (`doc_path`).
   - Release metadata (latest tag, published date) is discovered directly from
     the upstream repo using `github3.py`. When provided, release data drives
     version badges and release URLs; when absent we fall back to commit
     history as described earlier.
   - Optional manifest files (Cargo manifests, `pyproject.toml`, etc.) are
     fetched to build descriptive blurbs for the docs index.

2. **Local Snapshot (`config/pages.yaml`)**
   - All GitHub-sourced metadata is normalized into `config/pages.yaml`. This
     file acts as a frozen snapshot of the docs site at a point in time and is
     the single input to the generator/CI pipeline.
   - The snapshot includes per-page themes, release metadata, and layout hints
     so render steps never need to fetch unbounded state from GitHub.
   - To refresh the snapshot, run the bump tooling (see `pages bump` BDD
     coverage) which re-syncs release info and rewrites `config/pages.yaml`.

3. **Jinja Rendering from the Snapshot**
   - `PageContentGenerator` reads `config/pages.yaml`, fetches the referenced
     Markdown blob via GitHub (respecting releases or branches), and parses it
     into sections.
   - Jinja templates (`doc_page.jinja`, `docs_index.jinja`, `home_page.jinja`)
     consume the snapshot data plus parsed Markdown to produce HTML in
     `public/`.
   - Because all HTML is derived from the snapshot + committed documentation,
     reruns are deterministic: the rendered site only changes when GitHub
     content or the snapshot does.

This workflow lets GitHub stay the source of truth for docs while giving us a
checked-in configuration record that guarantees reproducible builds.

## Styling & Semantic Classes

### DaisyUI-First Abstraction

- The site styling layers Tailwind + DaisyUI. All components are built using
  DaisyUI’s semantic utility classes (`btn`, `badge`, `card`, etc.) instead of
  raw Tailwind primitives whenever possible.
- Semantic class names make Jinja templates easier to reason about (e.g., the
  docs sidebar uses `doc-nav__link` modifiers, headers use `section-title`,
  cards use `product-card`). These abstractions are documented in
  `documentation-style-guide.md`.
- Shared macros (see `partials/site_macros.jinja`) encapsulate the common
  header/footer markup so DaisyUI classes stay consistent across the marketing
  landing page, docs index, and individual doc pages.
- When authoring new components:
  1. Favor existing DaisyUI variants (`btn-primary`, `badge-outline`) before
     introducing bespoke classes.
  2. If a new semantic helper is required, define it once in CSS and reuse it
     throughout the templates.
  3. Tests such as `test_doc_prose_code_spans_have_expected_computed_style`
     validate that critical classes render with the expected computed styles.

This approach keeps presentation concerns declarative, makes templates more
readable, and reduces churn whenever Tailwind/DaisyUI upgrades land.

### Site Chrome Semantics

- The shared header/footer macros now rely on dedicated utility classes
  defined in `src/styles/site.css`—e.g., `.site-header`,
  `.site-header__inner`, `.site-header__brand`, `.site-header__nav`, and the
  corresponding `.site-footer*` helpers. This follows the Tailwind v4 and
  DaisyUI guidance referenced in `docs/tailwind-v4-guide.md` and
  `docs/daisyui-v5-guide.md`, keeping repeated utility stacks out of the
  templates.
- Main-content shells across `index.html`, `docs.html`, and every `docs-*.html`
  now use a shared `.site-main` base (padding, stacking context) with
  modifiers like `.site-main--home`, `.site-main--docs-index`, and
  `.site-main--doc` to encode their spacing/layout differences. When a new
  page variant appears, extend the semantic helper set instead of sprinkling
  raw `pt-*`/`flex` utilities so the macros keep these surfaces consistent.
- When extending the chrome, add new semantic helpers to the stylesheet once
  (instead of sprinkling raw utilities) and reference them via
  `partials/site_macros.jinja`. This ensures the landing page, docs index, and
  individual docs stay visually aligned while remaining easy to audit.

## OpenTofu Deployment Modules & Scripts

The infrastructure portion of df12 Pages lives under `modules/` and `deploy.tofu`.
We follow three core ideas:

1. **Split responsibilities by concern and provider.**
   - `modules/static_site` stands up the AWS primitives (S3 bucket, CloudFront,
     ACM certs, DNS records) with strong defaults (versioning, SSE, public
     access blocks).
   - `modules/deploy` (and its Scaleway sibling) performs the Git clone → Bun
     build → asset sync workflow using `null_resource` + `local-exec`, keeping
     build logic in deterministic shell scripts embedded in locals.
   - `modules/monitoring` hangs alarms on the distribution/Bucket endpoints so
     we get signal when deploys regress.

2. **Treat GitHub + Bun builds as part of the apply.**
   - The deploy module reads repo/branch/commit metadata from variables,
     clones the repo via HTTPS or SSH depending on credentials, installs deps
     with `bun install`, builds via `bun run build`, and syncs the generated
     `public/` tree to object storage.
   - Triggers (the current commit SHA) ensure OpenTofu re-runs the build only
     when content changes, not on every plan.

3. **Parameterize everything for multi-cloud.**
   - Each module exposes minimal inputs (`domain_name`, TLS settings, repo
     owner/name, distribution IDs). Provider-specific variants (e.g.
     `static_site_scaleway`, `deploy_scaleway`) implement the same interface so
     the root `deploy.tofu` can switch providers by swapping modules.
   - Scripts embedded in locals share a consistent structure (mktemp dir → clone
     repo → run commands → cleanup) so they’re easy to lint and reason about.

This modular layout lets us keep infrastructure code declarative, reuse deploy
logic across providers, and ensure the build pipeline remains reproducible from
source to CDN.
