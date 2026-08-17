# Migrate the Weaver sub-site to Tailwind v4 and daisyUI v5

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: IN PROGRESS

## Purpose / big picture

The Weaver sub-site (published at `/weaver/`) is the last large sub-site still
served by the **Tailwind Play CDN** — a browser script,
`https://cdn.tailwindcss.com`, that compiles Tailwind v3 utilities at page load
from an inline JavaScript configuration block repeated in three templates. Every
colour in the markup is spelled as a bespoke utility (`text-weaver-indigo`,
`bg-weaver-cream`) or an arbitrary value (`shadow-[2px_2px_0px_0px_rgba(25,60,110,1)]`),
and a 370-line hand-written stylesheet sits outside Tailwind's cascade layers
entirely.

After this change:

- Weaver builds like every other sub-site: one compiled stylesheet emitted by
  the repository's Tailwind v4 pipeline, no runtime CDN, no inline config.
- Colour is declared once, as a daisyUI v5 theme named `weaver`, and the markup
  refers to it semantically (`text-base-content`, `bg-primary`, `border-accent`)
  so a future palette change is a single-file edit.
- Every page renders with **no third-party runtime requests at all**: fonts,
  icons, and paper textures are served from `/weaver/assets/`.
- Every page passes an axe-core WCAG 2.2 AA scan with zero colour-contrast
  violations.
- The page chrome (sidebar, mobile drawer, head) is defined once instead of
  four times, so the legal pages gain the mobile navigation they currently
  lack.

Observable success: run `bun run build`, serve `public/`, load
`http://127.0.0.1:8080/weaver/` with the network throttled to block all
external hosts, and the page renders identically to today — same colours, same
typography, same hard-edged offset shadows — with `view-source:` showing a
single `<link rel="stylesheet">` to `/weaver/assets/styles/weaver.css` and no
`<script src="https://…">` anywhere.

## Constraints

Hard invariants. Violation requires escalation, not a workaround.

1. **Visual equivalence is the bar.** The migration is a re-plumbing, not a
   redesign. Computed styles for every element on every Weaver page must match
   the pre-migration baseline, except where a change is (a) an intentional
   contrast fix recorded in `Decision Log`, (b) an intentional chrome
   consolidation recorded in the same place, or (c) one of the bounded
   Tailwind v4 semantic changes enumerated in `Decision Log` under
   "accepted v4 semantics". Category (c) was added during Milestone 2 and is
   closed: it holds exactly one entry, the change from absolute to
   proportional line-height inheritance, whose measured effect is a shift of
   0.2% to 1.5% in page height on three of the seventeen pages and nothing at
   all on the other fourteen.
2. **Nothing under `public/` is edited by hand.** The published tree is
   generated; `public/` is git-ignored in its entirety. Sources are
   `src/styles/`, `src/static/`, `templates/`, and `config/pages.yaml`. See
   `AGENTS.md`, section "Repository layout".
3. **No other sub-site changes appearance.** `templates/mxd/`,
   `templates/netsuke/`, `templates/stilyagi/`, `src/styles/site.css`, and
   `src/styles/mxd.css` are out of scope. The shared page generator under
   `df12_pages/` may gain code only if Weaver genuinely cannot be expressed
   without it, and any such change must leave the other sites' output
   byte-identical.
4. **Colour literals live in exactly one file.** After the migration,
   `templates/weaver/**` and `src/styles/weaver/**` contain no hex codes and no
   `rgba(…)` literals. Every colour resolves through a daisyUI theme slot or an
   `@theme` token declared in `src/styles/weaver.css`. (Alpha compositing is
   expressed with Tailwind's `/` opacity syntax or `color-mix()`.)
5. **Tailwind utilities in markup must beat semantic classes.** Semantic
   classes are imported into `@layer components`; utilities land in
   `@layer utilities`. No unlayered rules, and no `!important` outside the
   existing full-bleed media query, whose behaviour is preserved verbatim.
6. **The commit gates pass at every commit.** `make all` must be green before
   each commit. Commits are small and each is independently valid.
7. **British English, Oxford spelling** in all prose and comments, per the
   repository's documentation style guide.

## Tolerances (exception triggers)

Stop and escalate when any of these is reached. Do not improvise past them.

- **Scope:** the plan touches roughly 25 files. If a milestone requires editing
  a file outside `templates/weaver/`, `src/styles/weaver*`,
  `src/static/weaver/`, `scripts/`, `tests/`, `config/pages.yaml`,
  `package.json`, `biome.jsonc`, or `docs/`, stop.
- **Generator changes:** if `df12_pages/**` needs a behavioural change, stop
  and escalate before writing it.
- **Dependencies:** one new dev dependency is budgeted
  (`@iconify-json/carbon`, for build-time icon extraction) plus font files
  vendored as binary assets. Any further dependency: stop.
- **Visual drift:** if a computed-style diff shows a change that is neither a
  planned contrast fix nor a planned chrome consolidation, stop and diagnose
  before continuing. Do not "accept the new look".
- **Contrast:** if clearing a WCAG 2.2 AA failure would require changing more
  than the token's own value — that is, if it needs a layout or hierarchy
  change — stop and escalate with the measured ratio and the options.
- **Iterations:** if the same computed-style or axe failure survives three
  fix attempts, stop and escalate.
- **Ambiguity:** if a Weaver colour has no honest daisyUI slot and no obvious
  `@theme` name, stop and present the options rather than inventing a slot.

## Risks

- **Risk:** the Play CDN is Tailwind **v3**; the build is Tailwind **v4**.
  Renamed utilities (`shadow-sm` → `shadow-xs`, `rounded-sm` → `rounded-xs`,
  `flex-shrink-0` → `shrink-0`, `bg-gradient-*` → `bg-linear-*`) and changed
  defaults (bare `border` is `currentColor` in v4, not `gray-200`) will shift
  rendering silently.
  Severity: high. Likelihood: high.
  Mitigation: the computed-style baseline in Milestone 0 is taken *before* any
  edit and diffed after every milestone; these renames are the first thing to
  check when a diff appears. A grep sweep for the known-renamed utilities is
  part of Milestone 2's checklist.
- **Risk:** Tailwind v4's preflight differs from v3's, so headings, lists, and
  `<pre>` may reset differently. `weaver-site.css` was written against the v3
  reset.
  Severity: high. Likelihood: medium.
  Mitigation: the baseline diff catches it. If preflight proves the culprit,
  the Episodic entrypoint (`src/styles/episodic.css` on branch
  `import-episodic-www`) shows the documented escape hatch: import
  `tailwindcss/theme.css` and `tailwindcss/utilities.css` separately and carry
  element defaults in a `layer(base)` partial. Prefer keeping preflight and
  fixing the partials; record the decision either way.
- **Risk:** the hand-written CSS couples to utility classes —
  `#sidebar nav a.bg-weaver-indigo.text-weaver-cream` and
  `a[href$="/install/"]` selectors. Replacing the utilities with semantic
  classes silently kills these rules.
  Severity: medium. Likelihood: high (it *will* happen if unnoticed).
  Mitigation: Milestone 4 rewrites the nav as a macro with explicit semantic
  classes *before* Milestone 5 removes the utility hooks.
- **Risk:** vermilion `#E8502B` on cream `#F3EFD9` measures roughly 3.2:1 and
  `weaver-faded` `#4A6FA5` roughly 3.9:1 — both below the 4.5:1 AA threshold
  for body text. Fixing them changes visible colour.
  Severity: medium. Likelihood: high.
  Mitigation: this is the anticipated, sanctioned exception to visual
  equivalence, exactly as the mxd migration handled it (commit `fad8da49`).
  Split each colour into a decorative token (unchanged, used for fills and
  rules) and a text token (darkened). Record every substitution with its
  before/after ratio.
- **Risk:** the Font Awesome removal is ~150 substitutions across 14 templates
  and is the largest mechanical change here. A wrong glyph is easy to miss.
  Severity: low (cosmetic). Likelihood: medium.
  Mitigation: it is a separate milestone with its own screenshot pass, and the
  mapping is generated from a checked-in table so it is reviewable as data.
- **Risk:** the `design-language.jinja` page is a standalone document with its
  own `<head>`, its own Tailwind config, and its own vocabulary. Folding it
  into the shared layout may not be behaviour-preserving.
  Severity: medium. Likelihood: medium.
  Mitigation: it is handled last, and if it resists, it keeps a bespoke layout
  that still uses the shared theme. That is an acceptable outcome; record it.

## Progress

- [x] (2026-08-17 16:45Z) Milestone 0 — Baseline capture and tooling.
- [x] (2026-08-17 17:00Z) Milestone 1 — Theme, entrypoint, and build wiring
      (red tests first).
- [x] (2026-08-17 18:40Z) Milestone 2 — Cut over to the compiled stylesheet;
      retire the Play CDN. The hand-written sheet moved to
      `src/styles/weaver/legacy.css` and is imported into the components
      layer, so the sub-site now has exactly one stylesheet link. Fourteen of
      seventeen pages are byte-identical by bounding box; three shift by
      0.2–1.5% for the reason recorded under "accepted v4 semantics".
- [ ] Milestone 3 — Self-host fonts and paper textures.
- [ ] Milestone 4 — Consolidate the page chrome; introduce the nav macro.
- [ ] Milestone 5 — Replace Font Awesome with inline Carbon SVG.
- [ ] Milestone 6 — Semantic-class sweep across the 16 templates.
- [ ] Milestone 7 — Fold `weaver-site.css` into layered partials.
- [ ] Milestone 8 — Accessibility audit and contrast fixes.
- [ ] Milestone 9 — Documentation and cleanup.

## Surprises & discoveries

- **Observation:** the walker snapshots are all but deterministic. Two captures
  of an unchanged page differ in exactly one property.
  Evidence: capturing `/weaver/why-weaver/` twice produced identical trees
  except `"opacity": "0.694981"` against `"opacity": "0.668446"` on the green
  `animate-pulse` status dot in the sidebar — the animation sampled at
  different points in its two-second cycle.
  Impact: the harness only has to normalize two things — `opacity` on animated
  nodes, and bounding boxes rounded to two decimal places — for a byte-exact
  comparison. Everything else can be compared literally, which makes the diff a
  far stronger gate than expected. Verified by capturing twice and diffing:
  seventeen pages compared, zero differing.
- **Observation:** the Play CDN's Tailwind v3 preflight is already visible in
  the baseline as `border-*-color: rgb(229, 231, 235)` on elements with no
  border colour of their own.
  Evidence: the `styleDiff` of the sidebar status dot in
  `.weaver-baseline/why-weaver.json`.
  Impact: confirms the anticipated v3-to-v4 risk is real and pervasive rather
  than theoretical. Tailwind v4 drops that implicit `gray-200` in favour of
  `currentColor`, so every element relying on it will move unless the
  Milestone 2 sweep catches it. The diff will name them precisely.
- **Observation:** seventeen Weaver pages are published, not the fifteen this
  plan first assumed, and the command sub-pages are nested.
  Evidence: `find public/weaver -name index.html` lists `commands/act/`,
  `commands/observe/`, `commands/verify/`, and the three legal pages.
  Impact: the harness derives its page list from the published tree, so the
  count corrects itself and stays correct as pages are added.
- **Observation:** the cutover diff is dominated by notation, not by change.
  Of the roughly 140,000 differing lines the first comparison reported, all
  but about 3,000 were the same styles spelled differently: v4 reports an
  opacity modifier as `oklab(...)` where v3 reported `rgba(...)`, composes
  `box-shadow` from more placeholder layers, and leaves an undrawn border at
  `currentColor` where v3's preflight said `gray-200` — on four and a half
  thousand nodes per page, of which forty draw a border at all.
  Evidence: normalizing each of those in `scripts/weaver_snapshot.py` took the
  report from 140,000 lines to 38,000 to a handful; the Oklab conversion is
  exact, with `oklab(0.359209 -0.0202858 -0.0934766 / 0.8)` and
  `rgba(25, 60, 110, 0.8)` canonicalizing to the same eight-bit triple.
  Impact: without this the gate would have been useless — the real findings
  were four regressions hiding among a hundred thousand lines of spelling. The
  normalization is unit-tested in both directions, since one that hides a real
  change is worse than none.
- **Observation:** every regression the cutover produced came from the same
  root cause, and it was the one the plan predicted.
  Evidence: the install link turned vermilion because moving the hand-written
  sheet into the components layer let `text-weaver-vermilion` beat the
  href-keyed rule that had been forcing it dark; the other four came from
  Tailwind v4 wrapping `space-y-*` in `:where()` and routing `text-*`
  line-height through `--tw-leading`, both of which let per-element utilities
  win arguments they used to lose.
  Impact: the risk register called this "it *will* happen if unnoticed" and
  scheduled the nav rewrite for Milestone 4 to avoid it. The diff caught all
  five without that help, which is a better outcome than the mitigation.
- **Observation:** `agent-browser screenshot` silently misfiles its output in
  two distinct ways — it reads a path given after `--full` as a selector, and
  it resolves relative paths against its own daemon working directory. It
  reports `✓ Screenshot saved to …` in both cases.
  Evidence: two consecutive runs of the screenshot pass reported success and
  left the output directory empty.
  Impact: the harness passes the path positionally and absolutely, and this is
  recorded in a comment beside the call so the next reader does not rediscover
  it. Any future screenshot automation in this repository should assert the
  file exists rather than trusting the exit status.

## Decision log

- **Decision:** adopt the Episodic stylesheet shape (layered partials, one
  compiled artefact) rather than the mxd shape (compiled sheet plus a
  hand-written companion sheet).
  Rationale: the user chose it when presented with both. It removes the
  unlayered-CSS cascade hazard permanently — the failure mode recorded in
  commit `b162aa45`, where an unlayered `* { padding: 0 }` reset silently
  zeroed every Tailwind spacing utility, since per CSS Cascade Level 5
  unlayered declarations always beat layered ones regardless of specificity or
  source order.
  Date/Author: 2026-08-17, planning session.
- **Decision:** scope includes contrast fixes, self-hosted fonts, Font Awesome
  removal, and normalizing accidental chrome inconsistencies.
  Rationale: the user selected all four, with the note that replicating
  accidental inconsistencies "is only making a rod for your back" and that any
  such change must be documented.
  Date/Author: 2026-08-17, planning session.
- **Decision:** icons become **build-time inline SVG**, not a runtime Iconify
  script.
  Rationale: Netsuke already migrated Font Awesome to Carbon icons and
  documents the mapping at `templates/netsuke/pages/icon-replacements.jinja`,
  but it renders them through `https://code.iconify.design`, which is still a
  runtime CDN. The brief is to *drop* the CDN, so Weaver extracts the same
  Carbon glyphs from the `@iconify-json/carbon` package at build time. This
  also matches the repository's existing "generated, not handwritten"
  convention for the Pygments stylesheets.
  Date/Author: 2026-08-17, planning session.

- **Decision:** write the validation harness as a Python Cyclopts CLI,
  `scripts/weaver_snapshot.py`, rather than the shell scripts this plan
  originally specified.
  Rationale: `docs/scripting-standards.md` makes Python with `uv` and Cyclopts
  the baseline for project scripts, and the existing scripts under `scripts/`
  follow it. Shell scripts would also sit outside the `ruff` and `ty` gates.
  The standard names `plumbum` for subprocess work, but no script or module in
  this repository uses it — `df12_pages/cli.py` and `df12_pages/deploy/`
  both use `subprocess` directly — so the harness follows the code rather than
  the letter of the document. Worth reconciling one way or the other, but not
  as part of this migration.
  Date/Author: 2026-08-17, Milestone 0.
- **Decision:** where Tailwind v4 newly honours a declaration that v3
  suppressed, pin the source to the value the page has always rendered rather
  than letting the declaration take effect.
  Rationale: Milestone 2's whole value is the claim that swapping the pipeline
  changed nothing, and that claim is worth more than any of the individual
  improvements on offer. v3 resolved several conflicts by source order or
  specificity in ways v4 deliberately corrects, so a handful of declarations
  that had never once applied were about to. Each is pinned to its rendered
  value *explicitly* — `leading-none` rather than deleting the leading
  utility, `mt-2` rather than `mt-4` — so the source now states what the page
  does instead of contradicting it. Anyone who prefers the suppressed values
  can have them in one legible commit.
  Instances: eleven hero headings and the design-language masthead, where
  `text-5xl lg:text-7xl` clobbered `leading-[1.1]`, `leading-[1.02]`, and
  `leading-tight`; two lead paragraphs where `lg:text-2xl` clobbered
  `leading-relaxed` (no single leading utility reproduces both breakpoints, so
  there the dead utility went); the sidebar's trailing divider block, whose
  `mt-4` lost to `space-y-2`'s more specific selector and rendered at 8px; the
  footer column headings, whose `mb-1` sat alongside the `space-y-2` gap
  rather than replacing it; `.content-section`, which asked for 2rem and
  rendered at the article's 1.5rem rhythm; and `code { font-size: 0.92em }`,
  which lost to the preflight's `font-size: 1em` and would have shrunk every
  inline code span on the site by eight per cent.
  Date/Author: 2026-08-17, Milestone 2.
- **Decision (accepted v4 semantics):** accept the change from absolute to
  proportional line-height inheritance.
  Rationale: v3's `text-sm` set `line-height: 1.25rem`, a length that
  descendants inherit as 20px whatever their own font size; v4 sets a unitless
  ratio, so a `text-[11px]` table header inside a `text-sm` region now sets at
  15.7px rather than 20px. Pinning it would mean adding an explicit
  `leading-*` to roughly 138 elements — writing v3's behaviour into the markup
  permanently, in service of nothing a reader would notice. Measured effect:
  table headers and small captions tighten by 1–9px; `commands/act/` loses
  81px of its 5,460 (1.5%), `sempai` and `jacquard` 26px each (0.2%); the
  other fourteen pages are unchanged. A before-and-after crop of the
  `jacquard` comparison table is identical but for the offset. No text changes
  size, colour, weight, or family.
  Date/Author: 2026-08-17, Milestone 2.
- **Decision:** pin Tailwind's stock palette to its v3 values for the
  twenty-seven shades the markup uses.
  Rationale: v4 redefined the default palette in OKLCH. The greys move by
  about one part in 255, but `green-400` goes from `#4ade80` to `#05df72` in
  forty-two places. Nearly all of these are syntax colours inside the dark
  code samples, which the semantic sweep will give proper `--color-code-*`
  names; pinning defers a palette decision to the milestone that owns it
  rather than making it by accident here.
  Date/Author: 2026-08-17, Milestone 2.
- **Decision:** return `scrollbar-color` to `auto` on `:root`.
  Rationale: daisyUI paints the root scrollbar through the standard property,
  and Chromium honours it in preference to the `::-webkit-scrollbar`
  pseudo-elements this sub-site has always used. Left alone, adopting daisyUI
  would have quietly replaced Weaver's cream-and-indigo scrollbar with
  daisyUI's. The `exclude: rootscrollgutter` plugin option covers a different
  feature and does not remove the rule.
  Date/Author: 2026-08-17, Milestone 2.
- **Decision:** fix the pre-existing failure in
  `tests/test_doc_generation.py::test_doc_prose_code_spans_have_expected_computed_style`
  rather than working around it, despite it being outside this migration.
  Rationale: `make all` was already red on this branch before any edit. The
  test guards on a Playwright Chromium build being installed, then invokes
  `css-view` without naming a browser; `css-view` defaults to Firefox, so on a
  Chromium-only machine the guard passes and the run then fails on a missing
  Firefox build. This is precisely the defect commit `68d6a2fa` fixed on branch
  `import-episodic-www`, which has not merged. Applying the same two-line fix
  here restores the commit gate that Constraint 6 depends on, and it is the
  same tooling this migration's harness uses. Flagged rather than folded in
  silently, since it is outside the stated scope.
  Date/Author: 2026-08-17, Milestone 0.
- **Decision:** exempt CSS longhand property names such as
  `border-bottom-color` from the en-GB spelling gate, via a pattern in
  `typos.local.toml`.
  Rationale: the plan and the stylesheets both have to quote property names
  such as `border-bottom-color`, which the CSS specification spells the
  American way. The pattern requires a leading segment, so a bare `color` in
  prose is still caught — verified against a probe file. Edits go in
  `typos.local.toml`, never `typos.toml`, which `make spelling` regenerates.
  Date/Author: 2026-08-17, Milestone 0.
- **Decision:** pin the capture browser to Chromium explicitly rather than
  accepting `css-view`'s default.
  Rationale: the same reasoning as commit `68d6a2fa`, which pinned the
  computed-style test in `tests/test_doc_generation.py`. A change to the tool's
  default would otherwise swap the rendering engine — and therefore the
  computed styles — out from under a comparison, and the resulting diff would
  look like a regression in the site.
  Date/Author: 2026-08-17, Milestone 0.

## Outcomes & retrospective

To be completed at the end of the work.

## Context and orientation

### What this repository is

`df12-www` builds a static site published from `public/`. Nothing under
`public/` is tracked in git. The build has five stages, run by
`bun run build` (see `package.json`):

1. `build:static` — `scripts/copy-static.ts` copies `src/static/**` into
   `public/**`, mirroring the directory layout. `src/static/weaver/assets/x`
   becomes `/weaver/assets/x`.
2. `build:css` — the Tailwind CLI compiles the entrypoints under
   `src/styles/`. Today there are two: `src/styles/site.css` becomes
   `public/assets/site.css`, and `src/styles/mxd.css` becomes
   `public/mxd/assets/tailwind.css`.
3. `build:images` — generates responsive image variants.
4. `build:pages` — `uv run pages generate --all-sites` renders the Jinja
   templates under `templates/` into HTML, driven by `config/pages.yaml`.
5. `build:search` — builds the Netsuke search index.

The commit gate is `make all`, which runs `build check-fmt lint test test-js
typecheck docs-check spelling`. Python is formatted by `ruff`, JavaScript, TypeScript
and **CSS** by Biome (`biome.jsonc`, with `css.parser.tailwindDirectives`
enabled so `@plugin` and `@utility` parse), Markdown by `mdformat-all` and
`markdownlint-cli2` (80-column wrap).

### What the Weaver sub-site is today

Templates live in `templates/weaver/`:

- `doc_page.jinja` (195 lines) — the base layout for the thirteen content
  pages. Emits the `<head>`, the fixed sidebar, and a `{% block content %}`.
- `home_page.jinja` (458 lines) — the `/weaver/` landing page. It does **not**
  extend `doc_page.jinja`; it repeats the entire head and sidebar.
- `shared_content_page.jinja` (89 lines) — the layout for generated legal
  pages. It repeats a *third*, slightly different head, and its sidebar is
  missing `id="sidebar"` and `data-mobile-nav-header`.
- `pages/*.jinja` (13 files) — content pages. Twelve extend `doc_page.jinja`.
  `pages/design-language.jinja` (737 lines) does not: it is a standalone
  document with a fourth copy of the head.

Styling comes from three places:

1. `https://cdn.tailwindcss.com` — the Play CDN, a runtime Tailwind **v3**
   compiler, configured by an inline `tailwind.config = {…}` block that
   declares five colours (`weaver-cream #F3EFD9`, `weaver-indigo #193C6E`,
   `weaver-vermilion #E8502B`, `weaver-dark #0F2440`, `weaver-faded #4A6FA5`),
   three font families (Playfair Display, IBM Plex Sans, IBM Plex Mono), and a
   grid background image. This block is duplicated in four templates and the
   copies are not identical.
2. `src/static/weaver/assets/styles/weaver-site.css` (370 lines) — hand-written
   and **unlayered**. It defines `:root` custom properties, the paper texture
   overlay, the offset-shadow "paper panel" look, callouts, status pills,
   full-bleed figure behaviour, the sidebar rules, the mobile drawer, and the
   legal-page components (`.content-toc`, `.content-card`).
3. Two more third-party runtime dependencies: Google Fonts
   (`fonts.googleapis.com`) and Font Awesome 6.4.0 (`cdnjs.cloudflare.com`),
   the latter loaded twice — once as CSS and once as the SVG-replacement
   script. There are also four `transparenttextures.com` background images.

Scale of the markup change: 2,646 occurrences of the five `weaver-*` colour
utilities across 16 templates (1,828 `weaver-indigo`, 432 `weaver-vermilion`,
310 `weaver-cream`, 58 `weaver-dark`, 18 `weaver-faded`), plus roughly 150 Font
Awesome icon elements drawn from 53 distinct glyphs.

`src/static/weaver/assets/js/mobile-nav.js` is a progressive-enhancement IIFE
that builds the hamburger button and backdrop at runtime; the CSS for those is
in `weaver-site.css`.

`config/pages.yaml` configures the site at line 1371 under `sites.weaver`:
`output_dir`, `templates_dir`, `stylesheet: assets/styles/weaver-site.css`,
`base_path`, theme metadata, and the navigation list.

### Reference implementations to imitate

- `src/styles/mxd.css` (on this branch) — the daisyUI theme block and `@theme`
  token conventions, including the practice of commenting *why* a token exists
  and what contrast ratio it clears.
- `src/styles/episodic.css` and `src/styles/episodic/*.css` (on branch
  `import-episodic-www`) — the layered-partial structure this plan adopts. Read
  it with `git show import-episodic-www:src/styles/episodic.css`.
- `tests/test_doc_generation.py`, the test at line 506 — the established
  pattern for a `css-view` computed-style assertion, marked
  `@pytest.mark.playwright` and guarded on a Chromium build being present.

### Terms used in this plan

- **Play CDN** — Tailwind's browser-side compiler, loaded from
  `cdn.tailwindcss.com`. Convenient for prototypes, wrong for production: it
  ships a compiler to every visitor and cannot be linted or version-pinned.
- **Cascade layer** — a CSS `@layer` grouping. Layers are ordered; a
  declaration in a later layer wins over an earlier one regardless of
  specificity. Declarations in *no* layer beat every layered declaration.
- **daisyUI theme slot** — one of daisyUI's semantic colour names (`primary`,
  `base-100`, `accent`, `neutral`, and their `*-content` pairs). Using
  `bg-primary` rather than `bg-[#193C6E]` is what "semantic class" means here.
- **`css-view`** — a CLI that loads a page in a headless browser and dumps
  computed styles as JSON, so styling can be diffed from a terminal. Invoked as
  `bun x css-view --mode walker --browser chromium <url>`.
- **agent-browser** — the browser-automation CLI used here for screenshots and
  for driving the axe-core scan.

## Plan of work

### Milestone 0 — Baseline capture and tooling

No source changes. Build the site as it stands and record what it looks like,
because every later milestone is judged against this.

Add `scripts/weaver_snapshot.py`, a re-runnable Cyclopts CLI with three
subcommands. `capture` serves `public/` on a local port, walks every published
Weaver page, and writes one `css-view` walker-mode JSON snapshot per page.
`shots` does the same with `agent-browser`, writing full-page screenshots at
360px, 768px, and 1440px. `diff` normalizes two snapshot directories and
reports per-page differences, exiting non-zero when any page changed.

The page list is derived from `public/weaver/**/index.html` rather than
hard-coded, so a page added to `config/pages.yaml` is captured without editing
the script. That yields seventeen pages, not the fifteen this plan first
assumed: the three generated legal pages (`code-of-conduct`, `privacy-policy`,
`terms-of-use`) are all published, and the command sub-pages are nested
(`/weaver/commands/act/`, not `/weaver/commands-act/`).

Snapshot output goes to `.weaver-baseline/` and `.weaver-baseline-shots/`;
`.weaver-*/` is git-ignored. The script is committed; its output is not.

Go/no-go: `capture` produces seventeen JSON files, `shots` produces fifty-one
PNG files, and — the property that makes the whole harness worth anything —
capturing twice in a row and diffing reports seventeen pages compared, zero
differing.

### Milestone 1 — Theme, entrypoint, and build wiring

**Red first.** Add `tests/test_weaver_build.py` with three tests that fail
today:

1. `test_weaver_stylesheet_is_compiled` — asserts
   `public/weaver/assets/styles/weaver.css` exists after a build and contains
   the string `--color-primary`.
2. `test_weaver_pages_have_no_cdn_references` — walks every generated file
   under `public/weaver/`, asserting none contains `cdn.tailwindcss.com`,
   `cdnjs.cloudflare.com`, `fonts.googleapis.com`, `code.iconify.design`, or
   `transparenttextures.com`.
3. `test_weaver_templates_declare_no_colour_literals` — greps
   `templates/weaver/**` and `src/styles/weaver*` for `#[0-9a-fA-F]{3,8}` and
   `rgba?(` and asserts no matches.

Mark all three `@pytest.mark.xfail(strict=True, reason="…")` and run them to
observe the expected failure, then remove the markers as each milestone turns
its test green. Tests 2 and 3 stay red until Milestones 5 and 6 respectively;
note that in the test docstring and in `Progress`.

Then create `src/styles/weaver.css`, modelled on `src/styles/episodic.css`:

```css
@layer theme, base, components, utilities;

@import "tailwindcss";

@source "../../templates/weaver/**/*.jinja";
@source "../static/weaver/assets/js/mobile-nav.js";

@plugin "daisyui" {
  themes: weaver --default;
  logs: false;
}

@plugin "daisyui/theme" {
  name: "weaver";
  default: true;
  prefersdark: false;
  color-scheme: light;
  /* … slots below … */
}

@theme {
  /* … tokens below … */
}
```

Proposed slot mapping, to be confirmed against the baseline and revised by the
Milestone 8 audit:

- `--color-base-100: #f3efd9` — the cream page ground.
- `--color-base-200`, `--color-base-300` — the two lighter panel surfaces the
  markup currently spells as `bg-white/50`, `bg-white/82`. Derive exact values
  from the baseline rather than guessing.
- `--color-base-content: #193c6e` — indigo is the body-text colour.
- `--color-primary: #193c6e` with `--color-primary-content: #f3efd9` — indigo
  is also the brand fill (active nav item, buttons).
- `--color-secondary: #0f2440` (`weaver-dark`) with cream content.
- `--color-accent: #e8502b` (vermilion) — decorative fills and rules.
- `--color-neutral: #0f2440` with cream content.
- Radii: the markup uses `rounded-sm` and `rounded-[2px]` almost exclusively,
  so `--radius-field: 0.125rem`, `--radius-box: 0.125rem`,
  `--radius-selector: 0.2rem`; `--border: 1px`; `--depth: 0`; `--noise: 0`.
  The Weaver look is hard-edged; daisyUI's default depth shading must be off.

`@theme` tokens for roles daisyUI does not model:

- `--color-faded: #4a6fa5` — the muted indigo, decorative use only.
- `--color-accent-text` — the darkened vermilion for text on cream. Value set
  by the Milestone 8 audit; expect roughly `#c63c1b`.
- `--color-ink-muted` — the darkened faded blue for muted *text*, likewise.
- `--font-display: "Playfair Display", serif`, `--font-sans: "IBM Plex Sans",
  sans-serif`, `--font-mono: "IBM Plex Mono", monospace`.
- `--shadow-block: 2px 2px 0 var(--color-primary)` and the two softer offsets
  the markup repeats (`4px 4px 0` and `8px 8px 0` at low alpha), replacing the
  twenty-six arbitrary `shadow-[…rgba(25,60,110,…)]` values.
- `--text-2xs: 10px`, `--text-3xs: 0.6875rem` — the `text-[10px]` (116 uses)
  and `text-[11px]` (22 uses) sizes.
- `--tracking-stamp: 0.3em`, `--tracking-label: 0.2em` — the `[0.3em]` (54) and
  `[0.2em]` (22) letter-spacings.

Wire the build: add to `package.json`

```json
"build:css:weaver": "bunx tailwindcss -i ./src/styles/weaver.css -o ./public/weaver/assets/styles/weaver.css --minify"
```

and chain it from `build:css` alongside `build:css:mxd`.

Go/no-go: `bun run build:css:weaver` emits a non-empty stylesheet; test 1 is
green; `make lint` accepts the new CSS (Biome parses the Tailwind directives).

### Milestone 2 — Cut over to the compiled stylesheet

In each of the four templates carrying a `<head>` (`doc_page.jinja`,
`home_page.jinja`, `shared_content_page.jinja`,
`pages/design-language.jinja`), delete the `<script src="https://cdn.tailwindcss.com">`
tag and the inline `tailwind.config` block, and replace the
`weaver-site.css` link with `/weaver/assets/styles/weaver.css`. Update
`config/pages.yaml` `sites.weaver.stylesheet` to
`assets/styles/weaver.css`. Note that `shared_content_page.jinja` builds its
link as `../{{ stylesheet or … }}`, a relative path where the others use
root-relative; normalize it to root-relative and record that as the first
documented chrome inconsistency.

`weaver-site.css` stays in place and keeps working for now — the compiled sheet
and the hand-written sheet coexist through Milestones 3 to 6. Only Milestone 7
retires it.

This is the milestone where Tailwind v3→v4 differences surface. Before running
the diff, grep the templates for the known renames and fix each:
`shadow-sm`→`shadow-xs`, `rounded-sm`→`rounded-xs` (check against the intended
radius — v4's `rounded-sm` is v3's `rounded`), `flex-shrink-0`→`shrink-0`,
`flex-grow`→`grow`, `bg-gradient-to-*`→`bg-linear-to-*`, and any bare `border`
that relied on v3's implicit `gray-200`.

Go/no-go: rebuild, re-capture, and diff against the Milestone 0 baseline. The
diff must be empty. This is the single most important gate in the plan: it
proves the compiled pipeline reproduces the CDN's output exactly, before any
semantic rewriting begins. Expect two or three rounds of chasing v4 renames
here; that is normal and is what the tolerance of three attempts per failure
refers to at the level of an individual property, not the milestone.

### Milestone 3 — Self-host fonts and paper textures

Vendor the three families as `woff2` under
`src/static/weaver/assets/fonts/`, following the Episodic naming convention
(`ibm-plex-sans-latin-wght-normal.woff2` and so on). Prefer variable fonts
where a family offers one: the templates use IBM Plex Sans at 300/400/500/600/700,
IBM Plex Mono at 400/500/600, and Playfair Display at 400/600/700/900, which is
twelve static faces or three variable ones.

Declare them with `@font-face` in a new `src/styles/weaver/site-base.css`
imported into `@layer base`, using `font-display: swap` and
`format("woff2-variations")` for variable faces. Add `<link rel="preload">` for
the two faces used above the fold (Playfair Display for the masthead, IBM Plex
Sans regular).

Do the same for the four `transparenttextures.com` PNG files — `cream-paper`,
`subtle-paper`, `cubes`, and whichever the fourth is: download once, place
under `src/static/weaver/assets/textures/`, and reference locally. Check the
licence of each and record it in the `Artefacts and notes` section; these
patterns are CC BY 3.0 and need attribution somewhere in the repository.

Go/no-go: diff against the Milestone 2 capture. Font metrics may shift by a
hair if the self-hosted subset differs from Google's; a sub-pixel difference in
`width` on text nodes is acceptable and should be recorded as a surprise, but a
change in `font-family`, `font-weight`, or line-box height is not.

### Milestone 4 — Consolidate the page chrome

This is the "remove accidental inconsistencies" milestone. Each change below is
a deliberate divergence from the baseline and must be listed in `Decision Log`
with a one-line justification.

Known inconsistencies found during planning:

1. `doc_page.jinja` repeats a ~230-character conditional class expression
   eleven times, once per nav link, to switch between active and inactive
   styling. Replace it with a Jinja macro `nav_link(href, index, label,
   active)` in a new `templates/weaver/_chrome.jinja`, emitting two semantic
   classes, `weaver-nav-link` and `weaver-nav-link--current`, plus
   `aria-current="page"`.
2. `weaver-site.css` styles the active nav item by *matching its utility
   classes* (`#sidebar nav a.bg-weaver-indigo.text-weaver-cream`) and
   special-cases the install link by href (`a[href$="/install/"]`). Both become
   ordinary rules on the semantic classes. The install link's distinct
   treatment (vermilion, monospace) is preserved but expressed as a macro
   argument rather than inferred from the URL.
3. `home_page.jinja` duplicates the head and sidebar instead of extending
   `doc_page.jinja`. Make it extend the shared layout and keep only its content
   block.
4. `shared_content_page.jinja` has a smaller inline Tailwind config (no
   `backgroundImage`), no Font Awesome, no texture overlay, no `id="sidebar"`,
   and no `data-mobile-nav-header` — which means `mobile-nav.js` bails out and
   **the legal pages have no working navigation below 1024px**. Make it use the
   shared layout, which fixes the drawer.
5. `pages/design-language.jinja` is standalone with a fourth head copy. Make it
   extend the shared layout too. If its content genuinely needs a different
   shell, give it a `{% block %}` override rather than a separate document; if
   even that fails, leave it standalone but sharing the theme, and record why.

Go/no-go: diff against Milestone 3. The diff will *not* be empty — that is the
point — but every difference must map to one of the five items above. The legal
pages gain a sidebar and drawer; the other pages should be unchanged.

### Milestone 5 — Replace Font Awesome with inline Carbon SVG

Add `@iconify-json/carbon` as a dev dependency. Write
`scripts/generate-weaver-icons.ts`, which reads a checked-in mapping table and
emits `templates/weaver/_icons.jinja`: a Jinja macro `icon(name, extra_class='')`
whose body is a `{% if %}` chain (or a dictionary lookup) returning inline
`<svg>` markup with `fill="currentColor"`, `aria-hidden="true"`, and
`focusable="false"`.

The mapping table is `config/weaver-icons.yaml`, listing each of the 53 Font
Awesome names against a `carbon:*` identifier. Seed it from the existing
Netsuke research at `templates/netsuke/pages/icon-replacements.jinja`, which
already maps 68 Font Awesome icons to Carbon and marks each as an exact,
near-exact, or creative substitution; the Weaver set is largely a subset. Any
Weaver glyph not in that table is chosen fresh and marked as such.

The generated file is committed (so the build has no network dependency) and
regenerated by the script — the same "generated, not handwritten" arrangement
the Pygments stylesheets use. Add a test asserting the committed file matches
what the script produces, so drift is caught by `make test`.

Then replace each `<i class="fa-solid fa-x"></i>` with `{{ icon('x') }}`, and
delete the two Font Awesome `<link>`/`<script>` tags and the
`window.FontAwesomeConfig` block.

Sizing note: Font Awesome glyphs are font-sized and inherit `font-size`;
Carbon SVGs need an explicit box. Give the macro a default `w-[1em] h-[1em]
inline-block align-[-0.125em]` so the substitution is metrically close, and
tune per-site where the baseline diff shows a shift.

Go/no-go: `test_weaver_pages_have_no_cdn_references` goes green. Screenshot
comparison at 1440px across all fifteen pages shows an icon in every place one
was before, at approximately the same size. A human reviews the icon grid; a
"creative substitution" that reads wrongly is a bug, not an accepted variance.

### Milestone 6 — Semantic-class sweep

The main event: 2,646 colour-utility occurrences become daisyUI semantics.

Work **one template at a time**, rebuilding and diffing after each. Do not
batch. The substitution table, to be confirmed once the Milestone 1 theme is
settled:

| Today | Becomes |
| --- | --- |
| `bg-weaver-cream` | `bg-base-100` |
| `text-weaver-indigo` | `text-base-content` |
| `bg-weaver-indigo` | `bg-primary` |
| `text-weaver-cream` | `text-primary-content` (on primary) or `text-base-100` |
| `border-weaver-indigo/20` | `border-base-content/20` |
| `text-weaver-vermilion` | `text-accent` (decorative) / `text-accent-text` (body copy — see Milestone 8) |
| `bg-weaver-vermilion` | `bg-accent` |
| `bg-weaver-dark` | `bg-neutral` |
| `text-weaver-dark` | `text-secondary` |
| `text-weaver-faded` | `text-ink-muted` |
| `shadow-[2px_2px_0px_0px_rgba(25,60,110,1)]` | `shadow-block` |
| `text-[10px]` | `text-2xs` |
| `tracking-[0.3em]` | `tracking-stamp` |

Ordering: start with the smallest template (`pages/why-weaver.jinja`, 218
lines) to validate the table end to end, then the rest in ascending size,
finishing with `pages/docs.jinja` (894 lines).

`weaver-indigo` is doing two jobs — body text and brand fill — and the split
between `base-content` and `primary` is a judgement call per occurrence. The
rule: if the colour is on text or a border, it is `base-content`; if it is a
filled surface the reader reads *against*, it is `primary`. When genuinely
ambiguous, prefer `base-content`, since that is what changes if the palette's
text colour ever moves.

Go/no-go after each template: the computed-style diff for that page's URL is
empty. After the last one, `test_weaver_templates_declare_no_colour_literals`
goes green.

### Milestone 7 — Fold `weaver-site.css` into layered partials

Split the 370-line sheet by concern into `src/styles/weaver/`:

- `site-base.css` (layer `base`) — `@font-face`, `::selection`, scrollbar
  styling, element defaults for `code` and `pre`.
- `chrome.css` (layer `components`) — sidebar, nav links, mobile drawer,
  texture overlay, grid background.
- `panels.css` — `.paper-panel`, `.masthead-frame`, `.masthead-eyebrow`,
  `.figure-frame`, `.spec-table`.
- `callouts.css` — `.reference-callout`, `.status-pill` and variants.
- `figures.css` — the full-bleed media query block, preserved verbatim
  including its `!important` declarations, which are load-bearing.
- `content.css` — `.content-toc`, `.content-section`, `.content-card` and
  parts (the legal pages).

Import them from `src/styles/weaver.css` in that order, each with an explicit
`layer(...)`. Replace every colour literal with a theme token as they move.
Delete `src/static/weaver/assets/styles/weaver-site.css` and remove its
`<link>`. Confirm `config/pages.yaml` no longer names it.

Go/no-go: diff is empty; `git grep -n 'weaver-site.css'` returns nothing;
`make all` is green.

### Milestone 8 — Accessibility audit and contrast fixes

Run axe-core against all fifteen pages via agent-browser, at 360px and 1440px
(the mobile drawer only exists at the narrow width, and its focus trap deserves
a check). Record every violation.

For each colour-contrast violation, measure the pairing, decide whether the fix
belongs to the decorative token or the text token, change the token value in
`src/styles/weaver.css` only, and re-measure. Log each substitution in
`Decision Log` in the style mxd used: old value, new value, old ratio, new
ratio, and which uses are affected.

Anticipated fixes, from the planning-stage estimates:

- Vermilion `#E8502B` as text on cream (~3.2:1) → a darker `accent-text`
  (~4.6:1). Decorative fills keep `#E8502B`.
- `weaver-faded #4A6FA5` as text on cream (~3.9:1) → a darker `ink-muted`.
- Any `text-weaver-indigo/70`-style transparency on cream: the alpha
  composite must be measured, not assumed. `text-base-content/70` over
  `#F3EFD9` lands near 4.2:1 and will likely need to become `/80`.

Also check non-colour findings the migration may have introduced: the icon
substitution must not have left an interactive control without an accessible
name, and the consolidated legal-page sidebar must not duplicate a landmark.

Go/no-go: zero axe violations on all fifteen pages at both widths. The
computed-style diff is non-empty and every entry corresponds to a logged
substitution.

### Milestone 9 — Documentation and cleanup

`AGENTS.md` currently states, in the Styling section, that "Netsuke and Weaver
load the **Tailwind Play CDN** at runtime" and that three sub-sites carry a
hand-crafted stylesheet and do not use daisyUI. Rewrite that passage: Weaver now
compiles from `src/styles/weaver.css` with a daisyUI `weaver` theme, and only
Netsuke and Stilyagi remain outside. Update the artefact table (line ~85) with
the new `weaver/assets/styles/weaver.css` row, and add the icon generator
alongside the Pygments generators in the "generated, never handwritten" list.

Update `docs/repository-layout.md` and `docs/developers-guide.md` for the new
`src/styles/weaver/` tree, the fonts and textures directories, and
`scripts/generate-weaver-icons.ts`.

Add `config/weaver-icons.yaml` and the texture licences to
`Artefacts and notes` below. Remove `.weaver-baseline*` directories. Confirm
`make all` passes from a clean tree.

## Concrete steps

All commands run from the repository root,
`/data/leynos/Projects/df12-www.worktrees/update-weaver`.

Set up and build:

```bash
make build
bun run build
```

Capture the baseline. Each subcommand serves `public/` itself, so no separate
server is needed:

```bash
uv run python scripts/weaver_snapshot.py capture .weaver-baseline
uv run python scripts/weaver_snapshot.py shots .weaver-baseline-shots
```

Expected: seventeen JSON files under `.weaver-baseline/` and fifty-one PNG
files under `.weaver-baseline-shots/`. A full capture takes about forty
seconds; the screenshots about fifty.

Diff after a milestone:

```bash
bun run build
uv run python scripts/weaver_snapshot.py capture .weaver-after
uv run python scripts/weaver_snapshot.py diff .weaver-baseline .weaver-after
```

Expected output when a milestone is behaviour-preserving:

```plaintext
code-of-conduct          no differences
commands                 no differences
...
17 pages compared, 0 differing.
```

Run the focused tests:

```bash
uv run pytest tests/test_weaver_build.py -v
```

Expected during Milestone 1 (red stage):

```plaintext
tests/test_weaver_build.py::test_weaver_stylesheet_is_compiled XFAIL
tests/test_weaver_build.py::test_weaver_pages_have_no_cdn_references XFAIL
tests/test_weaver_build.py::test_weaver_templates_declare_no_colour_literals XFAIL
```

Run the full gate before each commit:

```bash
make all
```

Run the accessibility scan (Milestone 8), via the agent-browser skill against
the served site, at 360px and 1440px for each of the fifteen URLs.

## Validation and acceptance

**Behavioural acceptance.** With `public/` served locally and the browser
configured to block every host except `127.0.0.1`:

- `http://127.0.0.1:8080/weaver/` renders the cream page, the indigo sidebar
  with its offset-shadow active item, the Playfair masthead, and the paper
  texture — indistinguishable from a screenshot taken before the migration.
- The page's HTML contains exactly one stylesheet link,
  `/weaver/assets/styles/weaver.css`, and exactly one script,
  `/weaver/assets/js/mobile-nav.js`.
- At 360px wide, `/weaver/privacy-policy/` shows a hamburger button that opens
  a modal drawer — behaviour that does not exist today.
- Every icon that was a Font Awesome glyph is now an inline `<svg>`; `view-source`
  contains no `<i class="fa-` anywhere.

**Test acceptance.** `uv run pytest tests/test_weaver_build.py` reports three
passed. Each test failed before its milestone and passes after; the red
failure is observed via `@pytest.mark.xfail(strict=True)`, and the marker is
removed as part of the green step.

**Quality criteria.**

- Tests: `make test` and `make test-js` pass; no test is skipped other than the
  Playwright-marked ones when Chromium is absent.
- Lint and format: `make lint` and `make check-fmt` pass. Biome accepts the new
  CSS partials.
- Types: `make typecheck` passes.
- Docs: `make markdownlint`, `make nixie`, and `make spelling` pass.
- Accessibility: axe-core reports zero violations on fifteen pages at two
  viewport widths.
- Styling: the final computed-style diff against the Milestone 0 baseline
  contains only entries traceable to a `Decision Log` line.

**Quality method.** `make all` is the gate. The computed-style diff and the
axe scan are run by hand at each milestone boundary and their transcripts
pasted into `Artefacts and notes`.

## Idempotence and recovery

Every step is re-runnable. `bun run build` is a full rebuild into a git-ignored
`public/`; deleting `public/` and rebuilding is always safe and is the first
thing to try when output looks stale.

The capture and diff scripts write only into their target directory and are
safe to re-run. Baseline directories are git-ignored and can be deleted at any
time — though the Milestone 0 baseline should be kept until Milestone 8
completes, since every later diff refers to it. If it is lost, recover it by
checking out the pre-migration commit into a second worktree, building there,
and capturing from that.

Each milestone is one or more small commits. Recovery from a bad milestone is
`git revert` of its commits followed by a rebuild and a diff to confirm the
baseline is restored.

The one irreversible-feeling step is deleting
`src/static/weaver/assets/styles/weaver-site.css` in Milestone 7. It is
tracked in git, so it is recoverable with `git show`; do not delete it until
the partials are in place and the diff is empty.

## Artefacts and notes

To be filled during execution: the Milestone 2 diff transcript (the critical
proof that the compiled pipeline matches the CDN), the axe violation table with
before and after ratios, the icon mapping table, and the texture licence
attributions.

## Interfaces and dependencies

New files:

- `src/styles/weaver.css` — the Tailwind v4 entrypoint. Declares the layer
  order, imports Tailwind and the partials, configures the daisyUI plugin, and
  holds the `weaver` theme and the `@theme` tokens. This is the **only** file
  in the sub-site containing a colour literal.
- `src/styles/weaver/{site-base,chrome,panels,callouts,figures,content}.css` —
  the semantic partials, imported into `layer(base)` or `layer(components)`.
- `templates/weaver/_chrome.jinja` — Jinja macros for the shared page
  furniture. At minimum:
  `{% macro nav_link(href, index, label, current=false, variant='') %}`.
- `templates/weaver/_icons.jinja` — generated. Exposes
  `{% macro icon(name, extra_class='') %}` returning inline SVG.
- `config/weaver-icons.yaml` — the Font Awesome to Carbon mapping, hand-curated
  and reviewed as data.
- `scripts/generate-weaver-icons.ts` — reads the mapping and
  `@iconify-json/carbon`, writes `templates/weaver/_icons.jinja`.
- `scripts/weaver_snapshot.py` — the validation harness, a Cyclopts CLI with
  `capture`, `shots`, and `diff` subcommands.
- `tests/test_weaver_build.py` — the three build-invariant tests plus the
  icon-generator drift test.

Modified files:

- `package.json` — adds `build:css:weaver` to the `build:css` chain and
  `@iconify-json/carbon` to `devDependencies`.
- `config/pages.yaml` — `sites.weaver.stylesheet` becomes
  `assets/styles/weaver.css`.
- `templates/weaver/**` — all sixteen templates.
- `biome.jsonc` — if the generated `_icons.jinja` or a partial needs an
  exclusion, following the pattern already used for the generated Pygments
  stylesheets.
- `AGENTS.md`, `docs/repository-layout.md`, `docs/developers-guide.md`.

Deleted files:

- `src/static/weaver/assets/styles/weaver-site.css`.

New runtime dependencies: none. The site ships fewer bytes and makes zero
third-party requests after this change.
