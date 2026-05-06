# Templatize sub-sites: mxd homepage, weaver, and netsuke

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
 `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`, `Decision Log`,
and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Status: COMPLETE

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

- [x] (2026-05-05) Phase 1: mxd homepage
  - [x] (2026-05-05) Extend `SubSiteHomePageBuilder` and update `cli.py`
  - [x] (2026-05-05) Create `templates/mxd/home_page.jinja`
  - [x] (2026-05-05) Add `homepage:` key to `sites.mxd` in `config/pages.yaml`
  - [x] (2026-05-05) Run `pages generate --site mxd`, validate, delete
        `public/mxd/index.html`
  - [x] (2026-05-05) Gate commit (`8c11192`)

- [x] (2026-05-05) Phase 2: weaver (14 pages)
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

- [x] (2026-05-05) Phase 3: netsuke (20 pages)
  - [x] (2026-05-05) Update netsuke `nav_links` to absolute paths in
        `config/pages.yaml`
  - [x] (2026-05-05) Create `templates/netsuke/doc_page.jinja`
  - [x] (2026-05-05) Create `templates/netsuke/home_page.jinja`
  - [x] (2026-05-05) Create 19 page templates in
        `templates/netsuke/pages/`
  - [x] (2026-05-05) Add `homepage:` and `content_pages:` to `sites.netsuke`
        in `config/pages.yaml`
  - [x] (2026-05-05) Run `pages generate --site netsuke`, validate, delete 20
        hard-coded HTML files
  - [x] (2026-05-05) Gate commit (this commit)

- [x] (2026-05-05) Review follow-ups for generated sub-site output
  - [x] (2026-05-05) Verified inline and outside-diff findings against current
        source templates and generated `public/` output.
  - [x] (2026-05-05) Patched still-valid findings in source templates instead
        of editing generated HTML directly.
  - [x] (2026-05-05) Regenerate affected Netsuke and Weaver pages.
  - [x] (2026-05-05) Validate generated HTML and browser behaviour with
        Playwright plus project gates.

- [x] (2026-05-05) Weaver sidebar footer parity follow-up
  - [x] (2026-05-05) Verified non-home Weaver content pages still lacked the
        sidebar footer `Back to df12 Productions` link present on the Weaver
        homepage.
  - [x] (2026-05-05) Patched `templates/weaver/doc_page.jinja` so generated
        content pages share the homepage sidebar footer back-link.
  - [x] (2026-05-05) Regenerate Weaver pages and validate the generated
        sidebar footer output.

- [x] (2026-05-05) Weaver homepage card accent follow-up
  - [x] (2026-05-05) Verified the Weaver homepage value-prop card corner
        accents still used `end-0` in both `templates/weaver/home_page.jinja`
        and generated `public/weaver/index.html`.
  - [x] (2026-05-05) Patched the three source template accents to use
        `start-0`.
  - [x] (2026-05-05) Regenerate Weaver and validate the generated homepage.

- [x] (2026-05-05) Content nav TypedDict follow-up
  - [x] (2026-05-05) Verified `_mark_current_nav()` still returned
        `list[dict[str, typ.Any]]` and assigned `dc.asdict(link)` directly.
  - [x] (2026-05-05) Added `_MarkedNavLink` and cast the `dc.asdict(link)`
        result before mutating the `current` and `href` fields.
  - [x] (2026-05-05) Validate the focused type and content-page behaviour
        gates.

- [x] (2026-05-05) Accessibility and generated-layout review follow-up
  - [x] (2026-05-05) Verified `_mark_current_nav()` still left non-current
        entries without an explicit `current` key after casting to
        `_MarkedNavLink`.
  - [x] (2026-05-05) Verified Netsuke install, Netsuke legal page, Weaver home,
        Jacquard, and Sempai findings against current generated output and
        mapped each still-valid issue back to a source template.
  - [x] (2026-05-05) Patched source templates and `ContentPageGenerator`
        minimally so regenerated output carries the accessibility, URL, and
        layout fixes.
  - [x] (2026-05-05) Regenerate affected Netsuke and Weaver pages.
  - [x] (2026-05-05) Validate exact generated output, browser behaviour, and
        project gates.

- [x] (2026-05-05) Weaver install daemon wording follow-up
  - [x] (2026-05-05) Verified the mixed daemon wording still existed in
        generated `public/weaver/install/index.html` and source
        `templates/weaver/pages/install.jinja`.
  - [x] (2026-05-05) Patched the source template to distinguish domain
        commands from capability probing.
  - [x] (2026-05-05) Regenerate Weaver and validate the generated install page.

- [x] (2026-05-05) Netsuke top-nav parent-link wording follow-up
  - [x] (2026-05-05) Verified Netsuke homepage navigation renders the
        configured `parent_link.label`, while `templates/netsuke/doc_page.jinja`
        hard-coded desktop content-page navigation as `&larr; df12`.
  - [x] (2026-05-05) Patched `templates/netsuke/doc_page.jinja` so desktop and
        mobile content-page parent links both render from `parent_link`.
  - [x] (2026-05-05) Regenerate Netsuke and validate the generated top-nav
        wording.

- [x] (2026-05-05) Netsuke generated-output review follow-up
  - [x] (2026-05-05) Verified the execplan review checklist and final gate
        summary were stale against the validation evidence elsewhere in this
        document.
  - [x] (2026-05-05) Verified the Netsuke generated-output findings against
        current templates and output: support controls, Plotly on the basic C
        example, the examples clone snippet, docs hub self-links, relative
        example links, hard-coded content nav links, and hard-coded content
        footer year were still valid.
  - [x] (2026-05-05) Patched the corresponding Netsuke source templates rather
        than editing generated HTML directly.
  - [x] (2026-05-05) Regenerate Netsuke and validate the generated pages.

- [x] (2026-05-06) Netsuke docs/sidebar and execplan review follow-up
  - [x] (2026-05-06) Verified the cited `SubSiteHomePageBuilder` examples and
        interface documentation were stale against the implemented constructor,
        which includes `base_path`.
  - [x] (2026-05-06) Verified the "Plan of work" section still used
        Stage/Step prose rather than the requested Phase/Step/Task dotted
        hierarchy.
  - [x] (2026-05-06) Verified the cited generated Netsuke HTML findings were
        still present in source templates, including sidebar duplicate targets,
        relative example links, the guides Plotly import, and the debug-guide
        self-link.
  - [x] (2026-05-06) Regenerate Netsuke and validate generated output plus
        project gates.

- [x] (2026-05-06) Netsuke docs interaction and copy follow-up
  - [x] (2026-05-06) Verified the Plan of work checkbox clarification,
        handwritten spelling, install copy button, target-name copy, manifest
        API CTA, qualitative security chart, and Basic C Manifest Reference
        route findings against current source templates and generated output.
  - [x] (2026-05-06) Patched the corresponding source templates and execplan
        text rather than editing generated HTML directly.
  - [x] (2026-05-06) Regenerate Netsuke and validate browser behaviour plus
        project gates.

- [x] (2026-05-06) Netsuke generated affordance follow-up
  - [x] (2026-05-06) Verified the Plotly script loading, Manifest Reference
        heading affordance, and Basic C breadcrumb findings against current
        source templates and generated output.
  - [x] (2026-05-06) Patched source templates so regenerated output defers
        Plotly loading, removes false heading permalink affordances, and makes
        the System Programming breadcrumb plain text.
  - [x] (2026-05-06) Regenerate Netsuke and validate browser behaviour plus
        project gates.

- [x] (2026-05-06) Execplan runtime notes and chart fallback follow-up
  - [x] (2026-05-06) Verified stale directory/runtime notes in the execplan and
        the missing Netsuke security-chart fallback against current code.
  - [x] (2026-05-06) Patched the execplan to describe the completed templated
        output pipeline and patched the source template to render a visible
        chart fallback.
  - [x] (2026-05-06) Regenerate Netsuke and validate browser behaviour plus
        project gates.

- [x] (2026-05-06) Netsuke no-JS security chart fallback follow-up
  - [x] (2026-05-06) Verified `securityChart` is seeded as an empty div in both
        the source template and generated page, and that the later line range is
        the runtime fallback for the same Plotly chart rather than a second
        chart container.
  - [x] (2026-05-06) Patch the source template, regenerate Netsuke, validate
        browser behaviour, and replay project gates.

- [x] (2026-05-06) Netsuke generated copyright year refresh
  - [x] (2026-05-06) Verified the multi-format generated page contains
        `&copy; 2026`, while `templates/netsuke/doc_page.jinja` uses
        `generated_at.year` and the page template extends it without overriding
        the footer.
  - [x] (2026-05-06) Found the same fixed-year source pattern in the Netsuke
        home-page and shared-content templates, which would keep regenerating
        fixed-year footer output for those page families.
  - [x] (2026-05-06) Regenerate Netsuke, search for stale `&copy; 2026`
        literals under `public/netsuke/`, validate, and commit the source fix;
        generated HTML still renders `2026` because the current generated year
        is 2026.

- [x] (2026-05-06) Generated public artefact untracking follow-up
  - [x] (2026-05-06) Verified modified tracked `public/` HTML, df12-pages
        metadata JSON, the Netsuke search index, and `public/mxd/assets/tailwind.css`
        are reproducible build output from `bun run build`, `pages generate`,
        and the configured static-site build scripts.
  - [x] (2026-05-06) Ignore and remove the verified generated artefacts from
        the Git index while keeping source docs, templates, config, static
        images, hand-maintained CSS, and JavaScript tracked.

## Surprises & discoveries

- Observation: Weaver page templates created by the Task agent used
  `{% extends "weaver/doc_page.jinja" %}` but the Jinja loader search path is
  `templates/weaver`, so the correct path is just
  `{% extends "doc_page.jinja" %}`. Evidence: Generator raised
  `TemplateNotFound: weaver/doc_page.jinja` on first run. Impact: Fixed with
  sed; all page templates updated before committing.

- Observation: On resume, Phase 3 was partially started but not wired into
  `config/pages.yaml`. Existing untracked Netsuke templates were
  `templates/netsuke/doc_page.jinja`, `templates/netsuke/home_page.jinja`, and
  10 content templates under `templates/netsuke/pages/`. Missing templates were
  the seven example-detail pages plus `guides`, `install`, and
  `icon-replacements`. Impact: continue from this partial state without
  reverting generated docs or template files.

- Observation: GrepAI is installed, but the `Projects` workspace search backend
  was unavailable during resume because Qdrant was not listening on
  `127.0.0.1:6334`. Impact: code exploration fell back to scoped exact/file
  inspection for this turn.

- Observation: The review suggestion for the Manifest Reference "Standard
  Library" sidebar link named `#standard-library`, but the current
  `templates/netsuke/pages/docs-templating-and-standard-library.jinja` page
  exposes `#stdlib-reference` for that section. Impact: the generated Manifest
  Reference link targets `#stdlib-reference` so the fragment resolves to a real
  section.

- Observation: The "View full API" CTA on the Manifest Reference page had no
  deeper full-API section to target. Impact: the CTA was removed instead of
  replacing one dead-end anchor with another.

- Observation: The first resumed `uv run pages generate --site netsuke` failed
  after writing the first 12 Netsuke pages because migrated documentation
  examples contained literal Jinja snippets such as
  `{{ src | basename | replace('.c', '.o') }}`. The site generator tried to
  evaluate those snippets and raised
  `TemplateAssertionError: No filter named 'basename'`. Impact: wrap lifted
  content bodies in `{% raw %}` / `{% endraw %}` blocks so examples render as
  documentation text.

- Observation: Several example-detail pages did not contain the
  `<!-- Main Content -->` marker used by the initial extraction helper, so the
  first generated templates for those pages had empty content blocks. Impact:
  regenerate missing page templates by extracting the first `<main>...</main>`
  block instead of depending on the optional comment marker.

- Observation: `uv run pages generate --site netsuke` now exits 0 and writes
  all 20 non-shared Netsuke pages plus the three shared pages. Evidence log:
  `/tmp/pages-generate-df12-www-templatize-sub-sites-netsuke.out`.

- Observation: Playwright spot checks at 1280x800 on
  `http://127.0.0.1:8081/netsuke/`, `/netsuke/install/`,
  `/netsuke/docs/getting-started/`, `/netsuke/examples/hello-world/`, and
  `/netsuke/blog/` rendered the expected pages with correct top-level active
  navigation. Screenshots were saved as `netsuke-home.png`,
  `netsuke-install.png`, `netsuke-docs-getting-started.png`,
  `netsuke-examples-hello-world.png`, and `netsuke-blog.png` by the Playwright
  MCP.

- Observation: The planned delete-and-regenerate pass completed successfully:
  all 20 hard-coded Netsuke HTML files listed in the plan were removed, then
  recreated by `uv run pages generate --site netsuke`. Evidence log:
  `/tmp/pages-regenerate-after-delete-df12-www-templatize-sub-sites-netsuke.out`.

- Observation: The first full `make test` gate failed with two unrelated
  issues after 43 tests passed: `test_build_env_sets_expected_keys` exposed
  that ambient `GITHUB_TOKEN` from the shell overrode the explicit
  `CredentialSet.github_token`, and the Playwright/css-view style test failed
  because css-view tried to launch a missing Firefox binary at
  `~/.cache/ms-playwright/firefox-1495/firefox/firefox`. Impact: fix
  `build_env` so explicit credentials override ambient provider-token
  variables, then rerun tests after addressing the browser runtime.

- Observation: After installing the exact Firefox build expected by css-view
  (`~/.cache/ms-playwright/firefox-1495`) and fixing `build_env`, `make test`
  passed: 45 tests passed with 2 deprecation warnings. Evidence log:
  `/tmp/test-df12-www-templatize-sub-sites.out`.

- Observation: Review comments against generated `public/` files mapped back
  to source templates in `templates/netsuke/` and `templates/weaver/`. Direct
  edits under `public/` would be overwritten by the next generator run, so
  still-valid generated-output findings are being fixed in templates and then
  regenerated. Date/Author: 2026-05-05 (review follow-up)

- Observation: The reported smooth-scroll issue in
  `public/weaver/roadmap/index.html` mapped to shared source in
  `templates/weaver/doc_page.jinja`, not the roadmap page template itself. The
  same unguarded pattern also existed in the standalone
  `templates/weaver/pages/design-language.jinja`, so both handlers now guard
  empty, `#`, invalid, and missing selectors before preventing default.
  Date/Author: 2026-05-05 (review follow-up)

- Observation: Playwright validation against a local static server on port
  8097 confirmed the Netsuke mobile menu starts closed and opens on click, the
  requested Netsuke sidebar and footer links render with corrected hrefs,
  duplicate head tags are absent from the Weaver design-language body, and the
  Weaver smooth-scroll handlers use guarded selectors. Date/Author: 2026-05-05
  (review follow-up)

- Observation: Validation gates passed after the review follow-ups:
  `make fmt`, `make check-fmt`, `make typecheck`, `make lint`, `make test`,
  `make markdownlint`, and `make nixie`. Evidence logs are under
  `/tmp/*-df12-www-templatize-sub-sites-review*.out`. Date/Author: 2026-05-05
  (review follow-up)

- Observation: Non-home Weaver generated pages still missed the sidebar footer
  `Back to df12 Productions` link because the link lived in
  `templates/weaver/home_page.jinja` only. `templates/weaver/doc_page.jinja`
  owns the sidebar for generated content pages, so the link belongs there too.
  Date/Author: 2026-05-05 (sidebar footer follow-up)

- Observation: `uv run pages generate --site weaver` regenerated all Weaver
  pages after the sidebar footer change. Exact checks and Playwright validation
  against a local static server on port 8098 confirmed the back-link appears on
  `/weaver/why-weaver/`, `/weaver/commands/act/`, and `/weaver/docs/` with
  `href="/"` and the same visual classes as the homepage. Date/Author:
  2026-05-05 (sidebar footer follow-up)

- Observation: The Weaver homepage value-prop card corner accents still used
  `bottom-0 end-0` in three places, which placed the accent on the wrong
  logical side. The source template now uses `bottom-0 start-0` for all three
  accents before regenerating `public/weaver/index.html`. Date/Author:
  2026-05-05 (homepage card accent follow-up)

- Observation: Exact checks and Playwright validation against a local static
  server on port 8099 confirmed all three Weaver homepage value-prop card
  accents now have `start-0`, none have `end-0`, and the affected cards are
  `Composable`, `Safe`, and `Fast`. Date/Author: 2026-05-05 (homepage card
  accent follow-up)

- Observation: The nav-marking type finding was still valid in
  `df12_pages/content_page.py`: `_mark_current_nav()` returned an unstructured
  `list[dict[str, typ.Any]]`, and the `dc.asdict(link)` value was mutated
  without a concrete shape. The new `_MarkedNavLink` mirrors `NavLinkConfig`
  plus the `current` flag that templates consume. Date/Author: 2026-05-05
  (content nav TypedDict follow-up)

- Observation: Validation for the content nav TypedDict follow-up passed:
  `make fmt`, `make check-fmt`, `make typecheck`, `make lint`,
  `uv run pytest -v tests/test_content_page.py`, `make test`,
  `make markdownlint`, and `make nixie`. Date/Author: 2026-05-05 (content nav
  TypedDict follow-up)

- Observation: `SubSiteHomePageBuilder` already marks a homepage nav link as
  current when its href matches the configured sub-site `base_path`, so the
  Netsuke home template only needed to remove its hard-coded `"/netsuke/"`
  fallback. Date/Author: 2026-05-05 (accessibility follow-up)

- Observation: The Jacquard footer layout drift mapped to shared
  `templates/weaver/doc_page.jinja`: Jacquard adds `xl:flex-row` through
  `main_extra_class`, so any footer inside `<main>` becomes part of the row
  layout. Moving the shared footer after the top-level flex wrapper keeps it
  below all generated content pages. Date/Author: 2026-05-05 (accessibility
  follow-up)

- Observation: The Netsuke terms-of-use asset and brand URL findings mapped to
  `templates/netsuke/shared_content_page.jinja`, which generates the shared
  legal pages. Date/Author: 2026-05-05 (accessibility follow-up)

- Observation: Playwright validation against a local static server on port
  8100 confirmed the Netsuke install header and mobile install links have
  `aria-current="page"`, the Netsuke terms page brand and asset URLs are
  root-relative as requested, Weaver home marks the Home sidebar link current,
  Jacquard's footer is a direct child of `<body>` and not inside `<main>`, and
  Jacquard/Sempai hash links update `location.hash`. Date/Author: 2026-05-05
  (accessibility follow-up)

- Observation: Validation for the accessibility follow-up passed:
  `make fmt`, `make check-fmt`, `make typecheck`, `make lint`,
  `uv run pytest -v tests/test_content_page.py tests/test_subsite_homepage.py`,
  `make test`, `make markdownlint`, and `make nixie`. Evidence logs are under
  `/tmp/*-df12-www-templatize-sub-sites-accessibility*.out`. Date/Author:
  2026-05-05 (accessibility follow-up)

- Observation: The Weaver install daemon wording finding mapped directly to
  `templates/weaver/pages/install.jinja`, so the generated page should be
  updated only by regenerating Weaver after the template edit. Date/Author:
  2026-05-05 (install wording follow-up)

- Observation: Weaver install wording validation passed: exact text checks and
  Playwright readback on local port 8101 confirmed
  `public/weaver/install/index.html` now says domain commands use a local
  daemon while capability probing runs in the CLI process. Gates also passed:
  `make fmt`, `make check-fmt`, `make typecheck`, `make lint`, `make test`,
  `make markdownlint`, and `make nixie`. Evidence logs are under
  `/tmp/*-df12-www-templatize-sub-sites-weaver-install-wording.out`.
  Date/Author: 2026-05-05 (install wording follow-up)

- Observation: Netsuke's homepage template already uses the configured
  `parent_link` for both desktop and mobile top navigation. The inconsistency
  came from the content-page base template, which duplicated the parent link
  rather than using the same context. Date/Author: 2026-05-05 (top-nav wording
  follow-up)

- Observation: The standalone Netsuke icon-replacements report also had a
  handwritten df12 breadcrumb. It is not part of the shared Netsuke nav chrome,
  but it receives `parent_link` from the generator, so it now renders that same
  configured label. Date/Author: 2026-05-05 (top-nav wording follow-up)

- Observation: Netsuke top-nav wording validation passed: exact checks found
  no generated `&larr; df12` or `← df12` top-nav labels, and Playwright
  readback on local port 8102 confirmed `/netsuke/`, `/netsuke/docs/`, and
  `/netsuke/icon-replacements/` render `← Back to df12 Productions`. Gates also
  passed: `make fmt`, `make check-fmt`, `make typecheck`, `make lint`,
  `make test`, `make markdownlint`, and `make nixie`. Evidence logs are under
  `/tmp/*-df12-www-templatize-sub-sites-netsuke-topnav-wording.out`.
  Date/Author: 2026-05-05 (top-nav wording follow-up)

- Observation: The docs hub self-link finding mapped to
  `templates/netsuke/pages/docs.jinja`; the target pages for the named cards
  already exist as generated pages or sections, so the fix can be static href
  updates without changing generator routing. Date/Author: 2026-05-05
  (generated-output review follow-up)

- Observation: The disabled Netsuke support controls had no published Discord
  target in the repository or config. The debug guide can point at the existing
  `#troubleshooting` section, while the Discord control should become plain
  "Discord coming soon" text to avoid presenting a fake action. Date/Author:
  2026-05-05 (generated-output review follow-up)

- Observation: Netsuke generated-output review validation passed. Exact checks
  confirmed the stale execplan checkbox and final gate summary were corrected;
  the Basic C example no longer loads Plotly; the examples hub clone snippet
  now uses `https://github.com/leynos/netsuke.git` and `cd netsuke/examples`;
  `templates/netsuke/doc_page.jinja` no longer defines `nav_items`; and the
  cited Hello World and Visual Design Assets pages no longer contain relative
  `../` or `../../` anchor hrefs. Playwright readback on local port 8103
  confirmed the docs hub card targets, the support callout action/text, the
  absence of Plotly on the Basic C example, and the absence of relative anchors
  on the Hello World example. Gates also passed: `make fmt`, `make check-fmt`,
  `make typecheck`, `make lint`, `make test`, `make markdownlint`, and
  `make nixie`. Evidence logs are under
  `/tmp/*-df12-www-templatize-sub-sites-netsuke-review-followup.out`.
  Date/Author: 2026-05-05 (generated-output review follow-up)

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

- Decision: Keep `templates/netsuke/pages/icon-replacements.jinja` as a
  standalone full HTML template rather than forcing it to extend
  `doc_page.jinja`. Rationale: the hard-coded
  `public/netsuke/icon-replacements/index.html` is a migration report page with
  no Netsuke nav, no mobile menu, no standard footer, and page-specific table
  styling. Wrapping it in the content-page base template would be a visual
  design change, violating the migration constraint. Date/Author: 2026-05-05
  (implementation resume)

- Decision: Preserve literal manifest/template snippets in Netsuke content
  templates by wrapping lifted content blocks in Jinja raw blocks. Rationale:
  snippets such as `{{ ins }}`, `{{ outs }}`, and `{{ path | shell_escape }}`
  are source examples for readers, not render-time expressions for the website
  generator. Date/Author: 2026-05-05 (implementation resume)

- Decision: Treat explicit credentials passed to `build_env` as authoritative
  for provider token environment variables, overriding ambient shell values.
  Rationale: deploy commands pass a resolved `CredentialSet`; letting unrelated
  process environment tokens win makes tests nondeterministic and can deploy
  with credentials other than those selected by the caller. Date/Author:
  2026-05-05 (gate fix)

- Decision: Use sub-site-prefixed root-relative legal links in the shared
  Netsuke and Weaver templates (`/netsuke/...` and `/weaver/...`) rather than
  bare top-level `/privacy-policy/` paths. Rationale: some review examples
  named bare root legal paths, but the surrounding findings asked for internal
  sub-site links to stay root-relative under the sub-site prefix. Date/Author:
  2026-05-05 (review follow-up)

## Outcomes & retrospective

All three targeted sub-sites are now generated from Jinja templates rather than
hand-authored HTML in `public/`. Phase 3 added the Netsuke homepage template,
the shared Netsuke content-page base template, and all 19 Netsuke content-page
templates, then wired those outputs through `config/pages.yaml`.

The final gate replay passed:

- `make fmt`
- `make check-fmt`
- `make typecheck`
- `make lint`
- `make test` (46 passed, 2 deprecation warnings)
- `make markdownlint`
- `make nixie`

Validation notes:

- `uv run pages generate --site netsuke` wrote all 20 non-shared Netsuke pages
  and the three shared pages.
- A delete-and-regenerate pass removed the old Netsuke HTML files and recreated
  them from templates.
- Playwright spot checks at 1280x800 covered `/netsuke/`, `/netsuke/install/`,
  `/netsuke/docs/getting-started/`, `/netsuke/examples/hello-world/`, and
  `/netsuke/blog/`.
- The css-view Playwright gate required the exact Firefox build expected by
  css-view (`firefox-1495`) to be present in the shared Playwright cache.

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
  mxd/                              — output dir; content generated from templates
  netsuke/                          — output dir; content generated from templates
  weaver/                           — output dir; content generated from templates
```

### How the build pipeline works

`pages generate --site {site}` calls `_generate_subsite(site_config, subsite)`
in `cli.py`. That function:

1. Renders doc pages from `subsite.pages`.
2. Renders the homepage if `subsite.homepage` is set.
3. Renders shared content (terms-of-use, privacy-policy, code-of-conduct) via
   `SharedContentGenerator`, using `templates/{site}/shared_content_page.jinja`.
4. Renders content pages (from `subsite.content_pages`) via
   `ContentPageGenerator`, using a per-page template that extends
   `templates/{site}/doc_page.jinja`.
5. Copies static assets from `subsite.static_assets_dir`.

### How homepages work

`SubSiteHomePageBuilder` loads `templates/{site}/home_page.jinja` and renders
it with a `homepage` dict (built from the YAML `homepage.context` block plus
`title`), `nav_links`, `parent_link`, and a `generated_at` timestamp. The
generator passes `nav_links=subsite.nav_links`,
`parent_link=subsite.parent_link`, and `base_path=subsite.base_path` so
home-page templates can render shared navigation and mark the current page.

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

### Historically hard-coded pages per site

At the start of this ExecPlan, these public pages were hand-maintained and
formed the migration inventory for the template conversion.

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

This section preserves the original roadmap; the `Progress` section above is
the completed execution record.

### Phase 1 — mxd homepage

#### Step 1.1 — Extend `SubSiteHomePageBuilder`

- [ ] **Task 1.1.1** Add optional keyword parameters
  `nav_links: list[NavLinkConfig] | None = None`,
  `parent_link: NavLinkConfig | None = None`, and
  `base_path: str | None = None` to
  `df12_pages.subsite_homepage.SubSiteHomePageBuilder.__init__`.
- [ ] **Task 1.1.2** Store the new values on the builder instance so `run()`
  can render shared homepage navigation.
- [ ] **Task 1.1.3** In `run()`, include `nav_links` and `parent_link` in the
  render context using `dc.asdict(...)`; import `dataclasses as dc` if needed.
  Depends on: 1.1.1, 1.1.2.
- [ ] **Task 1.1.4** Mark the homepage nav entry current when a nav link href
  equals `base_path`, keeping the current flag in the generated template
  context. Depends on: 1.1.1, 1.1.2.

#### Step 1.2 — Update `_generate_subsite`

- [ ] **Task 1.2.1** In `df12_pages/cli.py`, update the `_generate_subsite`
  homepage builder call to pass the sub-site navigation, parent link, and base
  path:

  ```python
  hp_path = SubSiteHomePageBuilder(
      subsite.homepage,
      templates_dir=templates_dir,
      nav_links=subsite.nav_links,
      parent_link=subsite.parent_link,
      base_path=subsite.base_path,
  ).run()
  ```

  Depends on: 1.1.1.

#### Step 1.3 — Create `templates/mxd/home_page.jinja`

- [ ] **Task 1.3.1** Lift the content from `public/mxd/index.html` into
  `templates/mxd/home_page.jinja` without changing the visible homepage body.
- [ ] **Task 1.3.2** Replace the hard-coded `<head>`, nav `<header>`, and
  `<footer>` with the equivalents from `templates/mxd/doc_page.jinja`.
- [ ] **Task 1.3.3** Render `nav_links` and `parent_link` from the template
  context, using the builder-provided current flag for active state. Depends
  on: 1.1.3, 1.1.4.
- [ ] **Task 1.3.4** Change homepage asset references from relative
  `assets/...` paths to absolute `/mxd/assets/...` paths.

#### Step 1.4 — Add homepage config to `config/pages.yaml`

- [ ] **Task 1.4.1** Under `sites.mxd`, add `homepage.title` with the value
  `Home — mxd`.
- [ ] **Task 1.4.2** Keep the homepage context empty because the mxd homepage
  template content is static.

#### Step 1.5 — Regenerate and validate

- [ ] **Task 1.5.1** Run `pages generate --site mxd`. Depends on: 1.2.1,
  1.3.1, 1.4.1.
- [ ] **Task 1.5.2** Use Playwright to visit
  `http://127.0.0.1:8080/mxd/` and capture a screenshot.
- [ ] **Task 1.5.3** Use `css-view` to compare the hero, nav, and footer
  computed styles against the planning reference; expected differences are zero.

#### Step 1.6 — Delete the hard-coded file

- [ ] **Task 1.6.1** Delete `public/mxd/index.html`. Depends on: 1.5.1,
  1.5.2, 1.5.3.
- [ ] **Task 1.6.2** Regenerate mxd and verify the deleted page is recreated
  from `templates/mxd/home_page.jinja`.

#### Step 1.7 — Gate commit

- [ ] **Task 1.7.1** Run `make fmt check-fmt typecheck lint test` sequentially.
  Depends on: 1.6.2.
- [ ] **Task 1.7.2** Commit the gated Phase 1 change with message
  `feat: template mxd homepage`. Depends on: 1.7.1.

______________________________________________________________________

### Phase 2 — weaver (14 pages)

#### Step 2.1 — Update weaver nav links to absolute paths

- [ ] **Task 2.1.1** In `config/pages.yaml`, under
  `sites.weaver.nav_links`, change all hrefs from relative (`../`) to absolute (
   `/weaver/`):

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

- [ ] **Task 2.1.2** Run `pages generate --site weaver` to confirm the existing
  `shared_content_page.jinja` still emits correct shared pages. Depends on:
  2.1.1.
- [ ] **Task 2.1.3** Spot-check
  `public/weaver/terms-of-use/index.html`; nav hrefs should be absolute.
  Depends on: 2.1.2.

#### Step 2.2 — Create `templates/weaver/doc_page.jinja`

- [ ] **Task 2.2.1** Create the base template for all weaver content pages at
  `templates/weaver/doc_page.jinja`.
- [ ] **Task 2.2.2** Include the full `<head>` with Font Awesome CDN, Tailwind
  CDN plus config block, Google Fonts link, and
  `<link rel="stylesheet" href="/weaver/assets/styles/weaver-site.css">`.
- [ ] **Task 2.2.3** Add the sidebar `<aside>` with the WEAVER brand, nav
  links rendered from `nav_links` context, active-state marking, and the
  `parent_link` back-link footer.
- [ ] **Task 2.2.4** Add a `<main>` element with
  `{% block content %}{% endblock %}` for page-specific body.
- [ ] **Task 2.2.5** Add the shared weaver `<footer>` block.
- [ ] **Task 2.2.6** Add the inline smooth-scroll `<script>` and
  `<script src="/weaver/assets/js/mobile-nav.js">`.
- [ ] **Task 2.2.7** Lift this structure from
  `public/weaver/why-weaver/index.html`, changing `../assets/` paths to
  `/weaver/assets/`.
- [ ] **Task 2.2.8** Expose named blocks `page_title` and `content`.

#### Step 2.3 — Create `templates/weaver/home_page.jinja`

- [ ] **Task 2.3.1** Lift `templates/weaver/home_page.jinja` from
  `public/weaver/index.html`.
- [ ] **Task 2.3.2** Include the full `<head>` used by
  `templates/weaver/doc_page.jinja`. Depends on: 2.2.2.
- [ ] **Task 2.3.3** Render sidebar nav from `nav_links` with Home marked
  active by the builder-provided current flag. Depends on: 1.1.4, 1.2.1.
- [ ] **Task 2.3.4** Preserve the full hero, value-props, commands preview,
  Sempai, links-grid sections, and weaver footer.
- [ ] **Task 2.3.5** Change relative asset references to `/weaver/assets/...`.
- [ ] **Task 2.3.6** Keep the homepage standalone because its sidebar footer
  and hero layout differ from `doc_page.jinja`.

#### Step 2.4 — Create 13 content page templates

- [ ] **Task 2.4.1** Create `templates/weaver/pages/{slug}.jinja` for each
  content page, extending `doc_page.jinja`. Depends on: 2.2.1.
- [ ] **Task 2.4.2** In every content template, fill `page_title` and
  `content` from the corresponding `public/weaver/{slug}/index.html`.
- [ ] **Task 2.4.3** Change relative `../assets/` references to
  `/weaver/assets/`.
- [ ] **Task 2.4.4** Use these page and template mappings:

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

- [ ] **Task 2.4.5** Use flat filenames such as `commands-act.jinja` for
  nested sub-command pages to avoid creating subdirectories in the `pages/`
  template folder; keep nested output paths in `output_slug`.

#### Step 2.5 — Add homepage and content_pages config to `sites.weaver`

- [ ] **Task 2.5.1** In `config/pages.yaml`, add `sites.weaver.homepage.title`
  as `Weaver — AI Codebase Tooling`.
- [ ] **Task 2.5.2** Add the full `sites.weaver.content_pages` list:

  ```yaml
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

#### Step 2.6 — Regenerate and validate

- [ ] **Task 2.6.1** Run `pages generate --site weaver`. Depends on: 2.3.1,
  2.4.1, 2.5.1, 2.5.2.
- [ ] **Task 2.6.2** Use Playwright to visit `/weaver/`,
  `/weaver/why-weaver/`, `/weaver/commands/`, `/weaver/commands/act/`, and
  `/weaver/safety/`; capture screenshots.
- [ ] **Task 2.6.3** Use `css-view` to diff the sidebar nav structure between
  the hard-coded and generated `why-weaver`; expect no differences.

#### Step 2.7 — Delete the 14 hard-coded files

- [ ] **Task 2.7.1** Delete the 14 Weaver hard-coded HTML files:
  `public/weaver/index.html`, `public/weaver/why-weaver/index.html`,
  `public/weaver/how-it-works/index.html`, `public/weaver/commands/index.html`,
  `public/weaver/commands/act/index.html`,
  `public/weaver/commands/observe/index.html`,
  `public/weaver/commands/verify/index.html`, `public/weaver/safety/index.html`,
   `public/weaver/sempai/index.html`, `public/weaver/jacquard/index.html`,
  `public/weaver/install/index.html`, `public/weaver/roadmap/index.html`,
  `public/weaver/docs/index.html`, and
  `public/weaver/design-language/index.html`. Depends on: 2.6.1, 2.6.2, 2.6.3.
- [ ] **Task 2.7.2** Regenerate Weaver and confirm the generated files match
  what was deleted.

#### Step 2.8 — Gate commit

- [ ] **Task 2.8.1** Run `make fmt check-fmt typecheck lint test`
  sequentially. Depends on: 2.7.2.
- [ ] **Task 2.8.2** Commit the gated Phase 2 change with message
  `feat: template weaver sub-site`. Depends on: 2.8.1.

______________________________________________________________________

### Phase 3 — netsuke (20 pages)

#### Step 3.1 — Update netsuke nav links to absolute paths

- [ ] **Task 3.1.1** In `config/pages.yaml`, under
  `sites.netsuke.nav_links`, use absolute hrefs: `/netsuke/`, `/netsuke/docs/`,
  `/netsuke/examples/`, `/netsuke/guides/`, and `/netsuke/blog/`.
- [ ] **Task 3.1.2** Regenerate Netsuke and spot-check shared content.
  Depends on: 3.1.1.

#### Step 3.2 — Create `templates/netsuke/doc_page.jinja`

- [ ] **Task 3.2.1** Create the base template for Netsuke content pages at
  `templates/netsuke/doc_page.jinja`.
- [ ] **Task 3.2.2** Include `<head>` content with Tailwind CDN, Iconify CDN,
  Google Fonts (Fraunces, JetBrains Mono, Source Sans 3), and
  `<link rel="stylesheet" href="/netsuke/assets/css/himotoshi.css">`.
- [ ] **Task 3.2.3** Add the fixed top `<nav>` with brand logo, desktop nav
  links from `nav_links`, active-state marking, GitHub/install action buttons,
  and mobile menu.
- [ ] **Task 3.2.4** Add `<main>` with
  `{% block content %}{% endblock %}`.
- [ ] **Task 3.2.5** Add the shared Netsuke `<footer>`.
- [ ] **Task 3.2.6** Add
  `<script defer src="/netsuke/assets/js/mobile-nav.js">`.
- [ ] **Task 3.2.7** Expose named blocks `page_title` and `content`.
- [ ] **Task 3.2.8** Lift from a representative content page such as
  `public/netsuke/install/index.html`, changing relative asset paths to
  `/netsuke/assets/...`.

#### Step 3.3 — Create `templates/netsuke/home_page.jinja`

- [ ] **Task 3.3.1** Lift `templates/netsuke/home_page.jinja` from
  `public/netsuke/index.html`.
- [ ] **Task 3.3.2** Keep the homepage standalone because it has a
  full-viewport hero with a background image and differs structurally from
  content pages.
- [ ] **Task 3.3.3** Change all relative asset references to
  `/netsuke/assets/...`.
- [ ] **Task 3.3.4** Preserve the homepage
  `assets/js/tailwind-config.js` and Plotly CDN includes verbatim.

#### Step 3.4 — Create 19 content page templates

- [ ] **Task 3.4.1** Create `templates/netsuke/pages/{name}.jinja` for each
  content page, using flat template names for nested output slugs.
- [ ] **Task 3.4.2** Use path segments in `output_slug` for nested output
  paths while keeping template filenames flat.
- [ ] **Task 3.4.3** Create these page templates:

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

#### Step 3.5 — Add homepage and content_pages config to `sites.netsuke`

- [ ] **Task 3.5.1** Add a `homepage:` block with title only to
  `sites.netsuke` in `config/pages.yaml`.
- [ ] **Task 3.5.2** Add the full `content_pages:` list to `sites.netsuke`,
  following the same pattern as Phase 2. Depends on: 3.4.3.

#### Step 3.6 — Regenerate and validate

- [ ] **Task 3.6.1** Run `pages generate --site netsuke`. Depends on: 3.3.1,
  3.4.3, 3.5.1, 3.5.2.
- [ ] **Task 3.6.2** Use Playwright to spot-check `/netsuke/`,
  `/netsuke/install/`, `/netsuke/docs/`, `/netsuke/docs/getting-started/`,
  `/netsuke/examples/hello-world/`, and `/netsuke/blog/`.
- [ ] **Task 3.6.3** Use `css-view` to diff the nav structure of the
  hard-coded and generated `install` page.

#### Step 3.7 — Delete 20 hard-coded HTML files

- [ ] **Task 3.7.1** Delete every `public/netsuke/*/index.html` and
  `public/netsuke/index.html` listed under "Currently hard-coded pages" above.
  Depends on: 3.6.1, 3.6.2, 3.6.3.
- [ ] **Task 3.7.2** Regenerate Netsuke and re-verify the deleted files are
  recreated from templates.

#### Step 3.8 — Gate commit

- [ ] **Task 3.8.1** Run `make fmt check-fmt typecheck lint test`
  sequentially. Depends on: 3.7.2.
- [ ] **Task 3.8.2** Commit the gated Phase 3 change with message
  `feat: template netsuke sub-site`. Depends on: 3.8.1.

## Concrete steps

All commands run from
`/data/leynos/Projects/df12-www.worktrees/templatize-sub-sites`.

### Phase 1 commands

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

### Phase 2 commands

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

### Phase 3 commands

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

**Phase 1 (mxd):**

- `pages generate --site mxd` exits 0 and prints `wrote public/mxd/index.html`.
- `http://127.0.0.1:8080/mxd/` renders identically to the reference screenshot
  (Playwright, viewport 1280×800).
- `css-view` diff of the `#hero-section` subtree shows zero differences between
  the hard-coded and generated page.
- `public/mxd/index.html` no longer exists in git.
- `make fmt check-fmt typecheck lint test` passes.

**Phase 2 (weaver):**

- `pages generate --site weaver` exits 0 and prints `wrote` lines for all 14
  non-shared pages.
- Playwright screenshots of `/weaver/`, `/weaver/commands/act/` match
  reference.
- No hard-coded `index.html` files remain in `public/weaver/` (confirmed by
  `git status` showing deletions).
- `make fmt check-fmt typecheck lint test` passes.

**Phase 3 (netsuke):**

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

`df12_pages.subsite_homepage.SubSiteHomePageBuilder.__init__` gains optional
navigation parameters:

```python
def __init__(
    self,
    config: SubSiteHomepageConfig,
    *,
    templates_dir: Path | None = None,
    nav_links: list[NavLinkConfig] | None = None,
    parent_link: NavLinkConfig | None = None,
    base_path: str | None = None,
) -> None: ...
```

The render context in `run()` gains:

```python
"nav_links": [dc.asdict(link) for link in (self.nav_links or [])],
"parent_link": dc.asdict(self.parent_link) if self.parent_link else None,
```

All callers in `cli.py` pass `nav_links=subsite.nav_links`,
`parent_link=subsite.parent_link`, and `base_path=subsite.base_path`.

### New template files (37 files total)

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

(37 new template files in total; the list above includes
`templates/netsuke/pages/guides.jinja` and
`templates/netsuke/pages/icon-replacements.jinja`.)
