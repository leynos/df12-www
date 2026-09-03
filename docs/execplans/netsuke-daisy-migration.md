# Migrate the Netsuke sub-site to Tailwind v4 and daisyUI v5

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: IN PROGRESS

## Purpose / big picture

The Netsuke sub-site (published at `/netsuke/`) is the last sub-site that
loads the **Tailwind Play CDN** — a browser script, `https://cdn.tailwindcss.com`,
that compiles Tailwind **v3** utilities at page load from a configuration
object in `src/static/netsuke/assets/js/tailwind-config.js`. That ships a
compiler to every visitor, cannot be linted or version-pinned, and resolves
cascade conflicts by source order in a way the compiled build does not. The
rest of the repository is on Tailwind v4 with daisyUI v5, compiled at build
time from one entrypoint per sub-site under `src/styles/`.

After this change Netsuke builds like every other sub-site: one compiled
stylesheet at `public/netsuke/assets/css/himotoshi.css`, emitted by
`build:css:netsuke` from `src/styles/netsuke.css`, with the palette declared
once as a daisyUI theme named `netsuke` and the markup referring to it
semantically. The hand-written `himotoshi.css` rules move into the components
layer, so a utility in the markup beats them the way anyone writing
`class="mt-8"` expects, and the doubled-selector idiom the Play CDN forced on
them becomes history.

Observable success: run `bun run build`, serve `public/`, load
`/netsuke/`, and the page renders identically to today — same colours, same
typography, same paper shadows — with `view-source:` showing no
`<script src="https://cdn.tailwindcss.com">` and no
`/netsuke/assets/js/tailwind-config.js`. The proof is a computed-style diff
against a baseline taken before any edit, chased to empty.

Issue: [#78](https://github.com/leynos/df12-www/issues/78). The Weaver
migration this follows is recorded in
`docs/execplans/weaver-daisy-migration.md`.

## Constraints

Hard invariants. Violation requires escalation, not a workaround.

1. **Visual equivalence is the bar.** Computed styles for every element on
   every Netsuke page must match the pre-migration baseline, except where a
   change is traced to a decision recorded in the `Decision log`.
2. **Nothing under `public/` is edited by hand.** The published tree is
   generated and git-ignored. Sources are `src/styles/`, `src/static/`,
   `templates/`, and `config/pages.yaml`.
3. **No other sub-site changes appearance.** The snapshot harness under
   `scripts/weaver_snapshot*.py` is shared and gains a `--site` parameter;
   its default stays `weaver`, so every existing Weaver command and test keeps
   meaning what it did.
4. **Tailwind utilities in markup must beat semantic classes.** The
   hand-written rules go into `@layer components`; nothing is left unlayered.
5. **The commit gates pass at every commit.** `make check-fmt lint typecheck
   test test-js` and, for Markdown, `make markdownlint nixie`.
6. **British English, Oxford spelling** in all prose and comments.

## Tolerances (exception triggers)

- **Scope:** the plan touches `templates/netsuke/`, `src/styles/netsuke*`,
  `src/static/netsuke/`, `scripts/`, `tests/`, `config/pages.yaml`,
  `package.json`, and `docs/`. A milestone that needs a file outside those
  stops.
- **Generator changes:** if `df12_pages/**` needs a behavioural change, stop
  and escalate.
- **Dependencies:** none are budgeted. Any new dependency stops.
- **Visual drift:** a computed-style difference that is neither notation nor
  traceable to a named decision stops the milestone until diagnosed.
- **Iterations:** if the same difference survives three fix attempts, stop.

## Risks

- **Risk:** the Play CDN is Tailwind v3 and the build is v4. Renamed
  utilities (`shadow-sm` → `shadow-xs`, `rounded-sm` → `rounded-xs`,
  `flex-shrink-0` → `shrink-0`, `flex-grow` → `grow`, `ring-opacity-*` →
  `/` syntax) and changed defaults (bare `border` is `currentColor` in v4, not
  `gray-200`; bare `ring` is 1px, not 3px) shift rendering silently.
  Severity: high. Likelihood: high. Mitigation: the baseline diff, and a
  sweep for the known renames before the cutover. The templates carry 193
  `shadow-sm`, 43 `flex-shrink-0`, 28 `flex-grow`, and 3 `ring-opacity-5`.
- **Risk:** the layer inversion. `himotoshi.css` is unlayered today and loses
  ties to the CDN's utilities on source order; in the components layer it
  keeps losing them, but the two doubled selectors (`.hm-hero.hm-hero`,
  `.hm-faux-window--card-bleed.hm-faux-window--card-bleed`) exist only to win
  those ties and will keep winning them. Severity: medium. Likelihood: high.
  Mitigation: the diff names the elements; the doubled selectors are retired
  once the layer does their job.
- **Risk:** v4 honours declarations v3 suppressed — `leading-*` under large
  `text-*`, a child `mt-*` under `:where()`-wrapped `space-y-*`, preflight
  element rules. Severity: medium. Likelihood: high. Mitigation: pin each to
  what the page rendered before, as Weaver did.
- **Risk:** Tailwind's stock palette moved to OKLCH in v4. The templates use
  `text-indigo-100` three times, and the `indigo` and `stone` names extend
  stock palettes. Severity: low. Likelihood: certain. Mitigation: pin
  `--color-indigo-100` to the v3 value.
- **Risk:** daisyUI emits every component, so any markup class matching a
  daisyUI component name is restyled the moment the compiled sheet is linked
  (Stilyagi had `timeline`, `card`, `status`, `tab`). Severity: medium.
  Likelihood: medium. Mitigation: the diff catches it; rename the class.

## Progress

- [x] (2026-09-03 13:20Z) Milestone 0: `--site` parameter added to the
      snapshot harness (`capture`, `shots`; page root, URLs, session name,
      readiness probe). Default stays `weaver`.
- [x] (2026-09-03 13:40Z) Milestone 0: `tests/support/netsuke_browser.py`
      and `tests/test_netsuke_browser.py` added, modelled on the Weaver
      browser suite. Four pre-existing 360px overflows waived by name.
- [x] (2026-09-03 14:40Z) Milestone 0: baseline captured twice and diffed:
      32 pages, zero differing, after three normalizer additions (see
      Surprises).
- [x] (2026-09-03 14:50Z) Milestone 0: baseline screenshots taken at 360,
      768 and 1440.
- [ ] Milestone 1: unify the Netsuke chrome (`home_page.jinja` extends
      `doc_page.jinja`), diff against the baseline, re-baseline.
- [ ] Milestone 2: red build-property tests; `src/styles/netsuke.css` with
      the `netsuke` theme and transitional tokens; `himotoshi.css` relocated
      into `layer(components)`; `build:css:netsuke` wired.
- [ ] Milestone 3: retire the Play CDN, v3→v4 renames, chase the diff to
      empty.
- [ ] Milestone 4: semantic-class sweep, convention tests, documentation.

## Surprises & discoveries

- **Observation:** two captures of the unchanged Netsuke site differed on
  four pages, where two Weaver captures differed on none. Evidence: the
  first `diff` reported `docs__rules-and-targets`, `docs__security`,
  `examples` and `guides` as differing. Three causes: an inline
  `style="background-image: url(/netsuke/assets/…)"` is reported by Chromium
  as an absolute URL carrying the loopback port the capture was given, which
  changes per run; Plotly numbers a chart's clip paths, defs and legend from
  a random six-hex-digit uid on every render, and the docs' security page
  draws one; and the guides hub carries an `animate-spin` icon whose
  `transform` — and whose child `<path>`'s bounding box — is sampled
  mid-rotation. Impact: `scripts/weaver_snapshot_normalize.py` now strips the
  loopback port from string values, the Plotly uid from ids and `url(#…)`
  references, and `transform` plus the bounding boxes of an animated node and
  its descendants. Each has a test in both directions. The plan had assumed
  the normalizer needed no change for Netsuke; it needed three.
- **Observation:** four Netsuke pages already scroll sideways at 360px.
  Evidence: `design/` lays out at 607px, `examples/batch-photo-processing/`
  at 363px, `examples/multi-format-documentation/` at 372px, and
  `examples/visual-design-assets/` at 385px, measured before any edit.
  Impact: the migration is meant to be inert, so it neither fixes nor worsens
  these. They are waived by page in `tests/support/netsuke_browser.py`, with
  the width each was measured at; the waiver asserts the overflow is still
  present and no wider, so it cannot outlive the defect. Fixing them is a
  visible change and a separate decision.
- **Observation:** `pages/icon-replacements.jinja` renders no chrome at all.
  Evidence: it carries its own `<head>`, no navbar, and inline arbitrary
  colour values. Impact: the browser suite checks it for fitting the viewport
  and for nothing about navigation.

## Decision log

- **Decision:** the harness's command surface gains `--site`, defaulting to
  `weaver`, rather than a copy of the harness for Netsuke.
  Rationale: the harness is eleven modules; a copy would drift, and the
  only site-specific parts are one path segment, one session name, and one
  probe URL.
  Date/Author: 2026-09-03, Claude.
- **Decision:** `_page_paths` takes the sub-site root; the command test's
  stand-in now accepts the argument it is passed.
  Rationale: a stand-in that ignored an argument the real function reads
  would pass while the command handed the wrong root.
  Date/Author: 2026-09-03, Claude.
- **Decision:** the four pre-existing 360px overflows are waived, not fixed.
  Rationale: Constraint 1. A fix changes what the page renders and belongs
  to whoever decides how the design page should lay out at phone widths.
  Date/Author: 2026-09-03, Claude.

## Outcomes & retrospective

To be written at completion.

## Context and orientation

The website is generated by `df12_pages`, a Python application that renders
Jinja2 templates under `templates/<site>/` against `config/pages.yaml`, into
`public/`, which is git-ignored build output. Netsuke's templates are
`templates/netsuke/doc_page.jinja` (the shared chrome every documentation and
content page extends), `templates/netsuke/home_page.jinja` (the homepage,
which today repeats the chrome), `templates/netsuke/shared_content_page.jinja`
(the legal pages), and one template per content page under
`templates/netsuke/pages/`.

Netsuke's stylesheet is `src/static/netsuke/assets/css/himotoshi.css`, a
1,560-line hand-written file copied verbatim into `public/`. Its last 150
lines are a marked block generated by
`scripts/generate_himotoshi_pygments_css.py` from the `HimotoshiStyle`
Pygments style. The Play CDN's theme extension lives in
`src/static/netsuke/assets/js/tailwind-config.js`: seven colour families with
sub-shades, three font families, one spacing step, and three paper shadows.

The snapshot harness is `scripts/weaver_snapshot.py` and its siblings. Its
`capture` records computed styles for every page via `css-view`, `shots`
records screenshots via `agent-browser`, and `diff` compares two captures
after normalizing away notation differences. Run it as:

```bash
uv run python scripts/weaver_snapshot.py capture --site netsuke .netsuke-baseline
uv run python scripts/weaver_snapshot.py shots --site netsuke .netsuke-shots
uv run python scripts/weaver_snapshot.py diff .netsuke-baseline .netsuke-after
```

`diff` exits 1 when any page differs and prints the first sixty lines of each
page's difference.

## Plan of work

Milestone 0 generalizes the harness and records the baseline; it is complete.

Milestone 1 makes `home_page.jinja` extend `doc_page.jinja`, moving its hero,
sections, and Plotly script into `content`, `extra_head`, and `extra_body`,
and deleting its copy of the head, nav, and footer. The diff against the
baseline is expected to show the homepage's nav becoming a list and its
footer gaining the Forthcoming link; each such difference is recorded below
and a fresh baseline is taken from the unified chrome.

Milestone 2 writes the build-property tests red, then `src/styles/netsuke.css`:
`@import "tailwindcss"`, `@source` directives for the templates and the
Netsuke scripts, the typography and daisyUI plugins, a `netsuke` theme, and
a `@theme` block carrying every Play CDN token under its current name and
value. `himotoshi.css` moves to `src/styles/netsuke/himotoshi.css` and is
imported with `layer(components)`; the Pygments generator's target follows
it. `build:css:netsuke` is added to `package.json` and chained into
`build:css`.

Milestone 3 removes the CDN and config scripts from `doc_page.jinja` and
`pages/icon-replacements.jinja`, deletes `tailwind-config.js`, applies the
v3→v4 renames, rebuilds, and chases the diff to empty.

Milestone 4 substitutes the transitional colour utilities for daisyUI
semantic classes, diffing after each template, retires the transitional
tokens, adds the convention tests, and updates `AGENTS.md`,
`docs/developers-guide.md`, and `docs/repository-layout.md`.

## Concrete steps

All commands run from the repository root.

```bash
bun install --frozen-lockfile
bun run build
uv run python scripts/weaver_snapshot.py capture --site netsuke .netsuke-baseline
# …edit…
bun run build
uv run python scripts/weaver_snapshot.py capture --site netsuke .netsuke-after
uv run python scripts/weaver_snapshot.py diff .netsuke-baseline .netsuke-after
make check-fmt lint typecheck test test-js
```

## Validation and acceptance

- `diff` reports `32 pages compared, 0 differing.` at the end of each
  milestone, or every differing page is traced to a decision recorded here.
- `tests/test_netsuke_build.py` passes without expected-failure markers: the
  compiled stylesheet exists and carries `--color-primary`; no built Netsuke
  page references `https://cdn.tailwindcss.com`.
- `tests/test_netsuke_browser.py` passes: every page shows the drawer toggle
  at 360px and the link list at 1440px, and fits the viewport except the four
  waived pages, which are asserted to still overflow.
- `make check-fmt lint typecheck test test-js markdownlint nixie` are green.

## Idempotence and recovery

Every step is re-runnable. `capture` and `shots` stage into a temporary
directory and publish atomically, so an interrupted run leaves the previous
snapshot intact. `bun run build` is safe to repeat; remove `public/` and
rebuild when a stale file needs clearing.

## Artefacts and notes

Milestone 0 evidence:

```plaintext
$ uv run python scripts/weaver_snapshot.py diff .netsuke-baseline .netsuke-baseline-2
…
32 pages compared, 0 differing.
```

## Interfaces and dependencies

No new dependencies. In `scripts/weaver_snapshot_paths.py`:

```python
DEFAULT_SITE = "weaver"

def _public_root(site: str = DEFAULT_SITE) -> Path: ...
```

`_css_view_argv`, `_capture_pages`, `_shoot_pages`, `_session_name`,
`_await_server`, `_start_server`, and `_served` each take a trailing
`site: str = DEFAULT_SITE`.
