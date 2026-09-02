# Developer's guide

This guide is for maintainers and contributors working on the df12 Productions
website generator, its sub-site templates, stylesheets, and browser-side
scripts. It covers how to build and serve the site locally, how generated and
hand-crafted files are separated, how the Pygments syntax highlighting for the
Episodic, Netsuke, and Stilyagi sub-sites are generated, the shared Jinja
macros and the component classes they pair with, the convention used for
browser-side components, the cascade quirks introduced by the Netsuke
sub-site's use of the Tailwind Play content delivery network (CDN), and how
accessibility is checked. It does not restate deployment or OpenTofu guidance,
which lives in [`AGENTS.md`](../AGENTS.md).

For the shape of the repository, see [Repository layout](repository-layout.md).
For the generator's architecture and extension points, see
[df12 Pages App Design](df12-pages-app-design.md). For Tailwind and daisyUI
conventions used by the main site, the mxd sub-site, and the Episodic sub-site,
see the [Tailwind v4 guide](tailwind-v4-guide.md) and the
[daisyUI v5 guide](daisyui-v5-guide.md). Documentation formatting itself
follows the [documentation style guide](documentation-style-guide.md).

## 1. Scope and audience

This document is the operating manual for people changing the generator, a
sub-site's templates or stylesheets, or a browser-side script — not the place
to relitigate why the system is shaped the way it is. Design rationale for the
generator lives in [df12 Pages App Design](df12-pages-app-design.md); design
rationale for a specific change lives in its execution plan under
`docs/execplans/`.

## 2. Build and serve

`bun run build` runs the full pipeline in a fixed order, because each step
depends on the last:

```bash
bun run build              # build:static, build:css, build:images, build:pages, build:search, build:static
bun run build:static       # copy src/static/ verbatim (scripts/copy-static.ts)
bun run build:css          # compile the main, mxd, Episodic, Weaver and Stilyagi Tailwind entrypoints
bun run build:css:mxd      # just the mxd entrypoint, for iterating on one sub-site
bun run build:css:episodic # just the Episodic entrypoint
bun run build:css:weaver   # just the Weaver entrypoint
bun run build:css:stilyagi # just the Stilyagi entrypoint
bun run build:images       # generate responsive image variants (scripts/generate-image-variants.ts)
bun run build:pages        # uv run pages generate --all-sites
bun run build:search       # build the Netsuke and Episodic search indices
bun run check:search       # fail when the committed Episodic index has drifted
```

`build:static` runs first because `build:images` reads the source images it
places. `build:pages` wraps the Python generator, which can also be driven
directly:

```bash
uv run pages generate --all-sites     # main site plus every sub-site
uv run pages generate --site netsuke  # one sub-site
```

`scripts/build-episodic-search-index.mjs` then reads the rendered
`public/episodic/` routes and the upstream-document manifest, writing the
committed MiniSearch projection at
`src/static/episodic/assets/search/episodic-search.json`. `build:search`
regenerates it once; `check:search` runs its `--check` mode without rebuilding
the payload. The final `build:static` copy publishes that projection to
`public/episodic/assets/search/episodic-search.json`. Run `bun run build` or
`bun run build:pages && bun run build:search && bun run build:static` after
changing an Episodic page or its documentation manifest. Run
`bun run check:search` in continuous integration (CI) or before committing an
index update to verify that the committed projection has not drifted.

`scripts/build_episodic_roadmap_data.py` projects the authoritative upstream
Episodic `docs/roadmap.md` into `templates/episodic/data/roadmap.jinja`. It uses
`scripts/episodic_roadmap_parser.py` to turn the Markdown into phase, step,
and task records, and `make site-data` runs it with
`--episodic-root $(EPISODIC_SOURCE)` before rebuilding the committed template.

`bun run dev` (or `make dev`, which builds once first) watches `src/**/*`,
`df12_pages/**/*`, `config/**/*`, `scripts/**/*`, and `pyproject.toml` with
`chokidar`, reruns `bun run build` on any change, and serves `public/` on port
8080 with caching disabled. `DF12_PORT` overrides the port, which matters when
several worktrees are served at once.

Because the watcher reruns the whole build, **no build step may write into a
directory it watches** — the build would trigger the watcher, which would rerun
the build, for as long as it was left running. The Episodic search index is the
one generated file that lives under `src/`, and
`scripts/build-episodic-search-index.mjs` skips its write when the content is
unchanged for exactly this reason; the watcher also ignores that directory as a
second guard. `test_a_build_does_not_rewrite_anything_the_dev_watcher_watches`
rebuilds an already-built tree and fails if anything under a watched root
moved, so a new step that writes into one is caught rather than discovered by
leaving `make dev` running.

A plain `http-server public/` — invoked directly, or via `bun run serve`, which
builds once and then serves without watching — has **no watcher**. Editing a
template, config file, or stylesheet after starting it has no effect on the
served output until `bun run build` (or `uv run pages generate`) is rerun by
hand. This is the usual reason a change appears not to have taken effect.

Run the commit gates with `make all`, which composes
`build check-fmt lint test test-js typecheck docs-check spelling` and runs them
sequentially rather than in parallel, since the build cache rewards sequential
runs. For a narrower check while iterating on the generator, templates, or
stylesheets:

```bash
make check-fmt lint typecheck
make test          # Python suite
make test-js       # JavaScript suite
```

For Markdown changes, run `make markdownlint` and `make nixie`. Rebuild and
inspect the rendered result as well — the gates do not render the site, so a
template change that passes every gate can still produce a broken page.

### 2.1. Bun is required

Bun is not optional tooling for this repository. It runs the build, the
JavaScript tests, and Biome, so `make lint`, `make fmt`, `make test-js`, and
`make dev` all fail without it. Install it from [bun.sh](https://bun.sh); the
Makefile checks for it by name and says so plainly when it is missing.

Those same targets depend on a `node_modules` stamp that runs
`bun install --frozen-lockfile`, so a fresh clone needs no separate install
step. The install is skipped unless `package.json` or `bun.lockb` has moved,
and the stamp is written only when bun exits cleanly, so a failed install is
retried rather than mistaken for a finished one.

### 2.2. Biome

Biome is the linter and formatter for everything that is not Python or
Markdown: JavaScript, TypeScript, JSON and JSONC, HTML, and the hand-crafted
CSS. It is pinned to an exact version in `devDependencies`, so every
contributor and every gate run agrees on what the rules are.

```bash
bun run lint:js       # biome check .  — formatter, linter, and import assists
bun run lint:js:fix   # biome check --write .  — apply what Biome can fix alone
```

`make lint` runs `ruff check` and then `bun run lint:js`. `make fmt` runs
`ruff format`, `ruff check --select I --fix`, `bun run lint:js:fix`, and
`mdformat-all`.

`biome check` is formatter, linter, and assists in a single pass, which has one
consequence worth remembering: **a misformatted script fails `make lint`, not
`make check-fmt`.** The target names do not imply that, so `check-fmt` carries
a comment saying where Biome's formatting is actually checked.

Run `make fmt` to apply what Biome can fix on its own, then review the findings
it leaves behind: Biome declines to make those changes unattended because they
alter what the code says rather than how it is laid out.

Where a rule genuinely should not apply, suppress it at the line with a stated
reason — `// biome-ignore lint/<group>/<rule>: why` — rather than loosening the
rule in `biome.jsonc`, which turns one considered exception into a silent
blanket. Biome rejects a reasonless suppression, and reports a suppression that
matches nothing, so a stale one will not sit there unnoticed.

`style/useForOf` is raised to an error above the recommended preset. That is
deliberate policy for this repository, not an inherited default.

### 2.3. TypeDoc

TypeDoc is the canonical documentation validator for TypeScript and ES modules
across df12 repositories. Here it runs in validation mode only — `emit` is
`none`, so it produces no site — and fails when anything it is asked to cover
lacks documentation.

```bash
bun run docs:check   # typedoc --options typedoc.json
make docs-check      # the same, in the gate; also part of `make all`
```

Two settings in `typedoc.json` do the work together, and neither is any use
alone. `validation.notDocumented` finds undocumented API;
`treatValidationWarningsAsErrors` turns that finding into a non-zero exit.
Without the second, TypeDoc reports the problem and exits zero, so the gate
looks configured and enforces nothing. `tests/js/typedoc-gate.test.mjs` pins
that behaviour against temporary fixtures.

`commentStyle` is `jsdoc`, so only `/** … */` counts as documentation; a plain
`/* … */` block is a comment. A module comment additionally needs an `@module`
tag, or TypeDoc attaches it to whatever declaration follows it and reports the
module as undocumented.

The entry points are the build-time module tree: `scripts/` and
`src/styles/plugins/`. The browser scripts under `src/static/` are outside it
deliberately. They are classic scripts — an IIFE assigning to a guarded
`module.exports` — so TypeDoc resolves the export object as an anonymous type
and asks for documentation on each synthetic member, down to names like
`export=.__type.createCopyController.__type.__type.toast.__type.announcer`.
Satisfying that would mean writing comments addressed to the type checker
rather than to a reader. Those modules are commented in the house style and
reviewed; see section 6.

#### Configuration boundaries

`biome.jsonc` carves several trees out of scope. Each exclusion is there
because the files are written by something other than a person, and every one
carries its reasoning in the file:

| Excluded                                                 | Why                                                                                                                                                                                                                                         |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/cassettes/`                                       | Betamax writes these HTTP recordings. A format gate over them would fail the moment anyone re-recorded a cassette.                                                                                                                          |
| `reference/`                                             | Kept snapshots, neither built nor shipped. Their value is that they still read the way they did when they were written.                                                                                                                     |
| `src/static/**/vendor`, `public/netsuke/assets/vendor`   | Third-party code. Not ours to restyle, and reformatting it would bury the next upstream diff.                                                                                                                                               |
| `src/static/episodic/assets/styles/syntax.css`           | The Pygments blocks are generated one rule per line. Formatting them would put the formatter and the generator in a loop, each undoing the other — see section 4.4. Only the formatter is disabled; the rest of each file is still checked. |
| `src/static/netsuke/assets/css/himotoshi.css`            | The Pygments blocks are generated one rule per line. Formatting them would put the formatter and the generator in a loop, each undoing the other — see section 4.4. Only the formatter is disabled; the rest of each file is still checked. |
| `src/static/stilyagi/assets/styles/syntax.css`           | The Pygments blocks are generated one rule per line. Formatting them would put the formatter and the generator in a loop, each undoing the other — see section 4.4. Only the formatter is disabled; the rest of each file is still checked. |
| `src/static/episodic/assets/search/episodic-search.json` | Episodic's MiniSearch builder owns the serialized index. Reformatting it would make the committed projection differ from its generator.                                                                                                     |
| `**/*.svg`                                               | The a11y rules that fire on standalone SVGs are written for inline JSX, where the `<svg>` is part of a document's accessibility tree.                                                                                                       |
| `**/*.css` (linter only)                                 | Formatting is enforced; the CSS lint rules are not, pending the stylelint decision.                                                                                                                                                         |

_Table 1: The trees `biome.jsonc` holds out of scope, and why each is written
by something other than a person._

Two parser settings matter as much as the exclusions.
`css.parser.tailwindDirectives` is enabled because the Tailwind v4 entrypoints
under `src/styles/` open with `@source`, `@plugin`, and `@theme`, which Biome's
CSS parser otherwise rejects as unknown at-rules — leaving both entrypoints
unparsed and silently skipped by the formatter. And `vcs.useIgnoreFile` is on,
so `.gitignore` is honoured; that is why `reference/` needs an explicit
exclusion despite being ignored, as the file kept inside it is negated back
into tracking.

## 3. Generated versus hand-crafted files

Everything under `public/` is build output and is git-ignored in its entirety.
Files placed there by hand are invisible to review and are lost the moment
anyone rebuilds from a clean tree.

Every published file has a source elsewhere in the repository:

| Published under `public/`             | Comes from                                            |
| ------------------------------------- | ----------------------------------------------------- |
| `**/*.html`                           | `df12_pages` rendering `templates/` against `config/` |
| `assets/site.css`                     | Tailwind compiling `src/styles/`                      |
| `mxd/assets/tailwind.css`             | Tailwind compiling `src/styles/`                      |
| `episodic/assets/styles/tailwind.css` | Tailwind compiling `src/styles/`                      |
| `weaver/assets/styles/weaver.css`     | Tailwind compiling `src/styles/`                      |
| `images/*.webp`, `images/*.avif`      | `scripts/generate-image-variants.ts`                  |
| `netsuke/assets/search/*.json`        | `scripts/build-netsuke-search-index.mjs`              |
| `episodic/assets/search/*.json`       | `scripts/build-episodic-search-index.mjs`             |
| everything else                       | `src/static/`, copied by `scripts/copy-static.ts`     |

_Table 2: Published paths under `public/` and the source that generates them._

In summary: hand-crafted assets — stylesheets, scripts, images, fonts, and
favicons — live under `src/static/`, whose layout mirrors the published tree
(`src/static/netsuke/assets/js/config-keys.js` is published at
`/netsuke/assets/js/config-keys.js`). Templates live under `templates/<site>/`
for each sub-site, and under `df12_pages/templates/` for the main site.
Tailwind entrypoints live under `src/styles/` and are compiled, not copied. See
[The site is generated](../AGENTS.md#the-site-is-generated)
in `AGENTS.md` for the full picture, including where page copy comes from.

Editing a file under `public/` directly is always a mistake: the next build —
local or in CI — discards it silently.

## 4. The Pygments CSS generators

This is the source of truth for how build-time syntax highlighting is wired
together on the Episodic, Netsuke, and Stilyagi sub-sites, referenced from the
[Netsuke update execution plan](execplans/netsuke-update.md).

### 4.1. Styles, lexers, and the highlight tag

Code blocks on the Episodic, Netsuke, and Stilyagi sub-sites are highlighted at
build time by the Jinja tag
`{% highlight '<lexer>'[, '<class>'] %} ... {% endhighlight %}`, implemented in
`df12_pages/jinja_highlight.py`. The tag dedents its body, runs it through
`pygments.highlight` with the named lexer, and wraps the result in a
`<div class="hm-syntax">` (or the named class, when a second argument is given)
using `pygments.formatters.html.HtmlFormatter`. Source text containing Jinja
syntax of its own — every `Netsukefile` example with `{{ ins }}` placeholders —
must be wrapped in `{% raw %}` inside the tag.

Three Pygments styles supply the colours:

- `EpisodicStyle` in `df12_pages/episodic_highlighting.py`, for the Episodic
  sub-site.
- `HimotoshiStyle` in `df12_pages/highlighting.py`, for the Netsuke sub-site.
  The module also defines `NetsukeLexer` (YAML with embedded Jinja, for
  `Netsukefile` manifests) and `NetsukeConsoleLexer` (`$`-prompted shell
  sessions with backslash continuation), both thin subclasses of stock Pygments
  lexers.
- `StilyagiStyle` in `df12_pages/stilyagi_highlighting.py`, for the Stilyagi
  sub-site.

`EpisodicStyle` is imported directly by the Episodic generator. The Netsuke
custom lexers and the `HimotoshiStyle` and `StilyagiStyle` classes are
registered with Pygments through the `pygments.lexers` and `pygments.styles`
entry points in `pyproject.toml`, so `get_lexer_by_name("netsuke")` and
`get_style_by_name("stilyagi")` resolve anywhere in the pipeline without an
explicit import.

### 4.2. The shared helper and the division of responsibility

`scripts/pygments_css.py` provides
`token_rules(formatter, style, css_class, prefix, bold_weight)`, the single
translation from a Pygments `Style` to CSS rules, shared by
`scripts/generate_episodic_pygments_css.py`,
`scripts/generate_himotoshi_pygments_css.py`, and
`scripts/generate_stilyagi_pygments_css.py`. The generated `:root` variables
and token rules are shared output. Site-specific chrome stays at each site's
established boundary: Himotoshi's remains in its generator, while Stilyagi's
layout rules for `.code-scroll`, `.stilyagi-syntax`, and `.stilyagi-syntax pre`
are handwritten above the `BEGIN` marker in `syntax.css`.

The module exports two functions. Everything else in it is private and may be
reshaped freely.

`token_rules(formatter, style, css_class, prefix, bold_weight)` returns a
`(variables, rules)` pair: the `:root` custom-property declarations and the
selector rules, both as lists of lines in the style's own declaration order.
That order is load-bearing rather than cosmetic — a subtype's rule must follow
its ancestor's to win at equal specificity, which holds as long as the style
declares parents before children. The `formatter` must already be bound to
`style` because it supplies the resolved token list and class prefix. The
shared helper resolves token classes without a private Pygments method: it
walks each token's parent chain and uses the public `STANDARD_TYPES` mapping,
preserving Pygments' class strings.

The Stilyagi generator emits only the `:root` variables and token rules. Its
layout rules stay outside the marked block so padding, scrolling, and chrome
can be edited directly as CSS.

`variable_name(token, prefix)` derives one custom-property name from a Pygments
token type: `Literal.String.Escape` with the prefix `--netsuke-syntax-` gives
`--netsuke-syntax-literal-string-escape`. Underscores become hyphens, and the
bare `Token` type, having no dotted tail, becomes `text`. `token_rules` calls
it for every declared token, so a generator rarely needs it directly; it is
exported for the case where one has to name a variable outside the generated
block, and to keep the naming rule in one place rather than reimplemented at a
call site.

The three parameters that differ between the sub-sites are held as constants at
the top of each generator — `CSS_CLASS`, `VARIABLE_PREFIX`, and `BOLD_WEIGHT` —
and every selector the generator emits interpolates `CSS_CLASS` rather than
spelling the wrapper class out. The chrome rules did spell it out until
recently, which meant a renamed wrapper would have half-applied: the token
rules would follow the constant and the chrome would not.

### 4.3. Why tokens are grouped under their nearest declared ancestor

**Normative:** treat `token_rules` as the only correct way to turn a Pygments
`Style` into CSS. Do not hand-write a rule per declared token.

Pygments emits the _most specific_ class it holds for a token in the rendered
markup — `c1` for a single-line comment, `s2` for a double-quoted string, `mi`
for an integer — while a `Style` typically declares only broad categories
(`Comment`, `Literal.String`, `Number`) and lets the specific subtypes inherit
from them. A generator that emits one CSS rule per token the style declares
therefore leaves most of the classes that actually appear in the markup
unstyled. The failure is silent: an unstyled token does not error or go blank,
it renders in the block's default text colour, which reads as merely
uninteresting rather than obviously wrong. This exact defect shipped on
twenty-one Netsuke pages — comments, strings, numbers, and keyword constants
all rendering at body colour — before it was found; see the addendum to the
[Netsuke update execution plan](execplans/netsuke-update.md). `token_rules`
exists specifically to close this gap for all three sub-sites, and
`scripts/pygments_css.py`'s module docstring documents the same risk for
Stilyagi.

`token_rules` resolves this by walking every token Pygments' `HtmlFormatter`
knows about and finding the nearest ancestor the style actually declares a
colour for (`_nearest_declared`, walking the Pygments token's `parent` chain),
then emitting one CSS rule per declared token that covers every subtype class
that inherits from it. Declaration order in the style's `styles` mapping is
preserved in the output, which matters beyond tidiness: at equal specificity a
later rule wins, so a subtype's rule must follow its ancestor's — this holds as
long as the style declares parents before children.

### 4.4. Normative rules

- Never hand-edit CSS between a generator's `/* BEGIN generated ... */` and
  `/* END generated ... */` markers. The next generator run discards it. This
  has already happened once, to a small-mobile type-scale media query that was
  added inside the marked block by hand; it is why that rule is now emitted by
  `generate_himotoshi_pygments_css.py` itself, alongside the generated token
  rules.
- Rerun the relevant generator after any change to `EpisodicStyle`,
  `HimotoshiStyle`, or `StilyagiStyle`.
- The generators write to the tracked source under `src/static/` —
  `src/static/episodic/assets/styles/syntax.css`,
  `src/static/netsuke/assets/css/himotoshi.css`, and
  `src/static/stilyagi/assets/styles/syntax.css` — never to `public/`. Writing
  to `public/` would lose the change on the next clean build.
- A test asserts the committed marked block matches what the generator would
  produce (`test_committed_stylesheet_matches_the_generator` in each test
  module below). A stale stylesheet fails the commit gates.
- All three generated stylesheets are excluded from the Biome formatter, in the
  `src/static/stilyagi/assets/styles/syntax.css`,
  `src/static/netsuke/assets/css/himotoshi.css`, and
  `src/static/episodic/assets/styles/syntax.css` override in `biome.jsonc`.
  `token_rules` emits one rule per line, which the formatter would expand; the
  next generator run would collapse it again, and the tools would undo each
  other on alternate runs — with the test above failing on whichever ran last.
  Formatting is the generator's output shape, so if it needs to change, change
  `scripts/pygments_css.py` and regenerate. Do not remove the exclusion to tidy
  a diff.

### 4.5. Regenerating and verifying

```bash
uv run python scripts/generate_episodic_pygments_css.py
uv run python scripts/generate_himotoshi_pygments_css.py
uv run python scripts/generate_stilyagi_pygments_css.py
uv run pytest tests/test_episodic_highlight.py tests/test_netsuke_highlight.py tests/test_stilyagi_highlight.py
bunx biome check src/static/episodic/assets/styles src/static/netsuke/assets/css src/static/stilyagi/assets/styles
```

Each script is idempotent: rerunning it without changing the corresponding
style leaves the stylesheet untouched, and it reports whether it wrote a
change. The Biome check confirms the hand-written stylesheets beside each
generated one are still formatted, and that the exclusion is holding: it should
report the generated files as unchanged rather than reformatting them.

Regenerating is also how to recover a generated stylesheet that has been
reformatted or otherwise edited by mistake — the script rewrites the marked
block outright, so a run restores it without needing the previous content.

### 4.6. Per-site mapping

| Site     | Style            | Lexers                                             | Wrapper class     | Variable prefix      | Bold weight | Stylesheet                                     |
| -------- | ---------------- | -------------------------------------------------- | ----------------- | -------------------- | ----------- | ---------------------------------------------- |
| Episodic | `EpisodicStyle`  | `bash`, `console`, `json`, `make`, `xml`           | `episodic-syntax` | `--episodic-syntax-` | `600`       | `src/static/episodic/assets/styles/syntax.css` |
| Netsuke  | `HimotoshiStyle` | `netsuke`, `netsuke-console`, `toml`, `powershell` | `hm-syntax`       | `--netsuke-syntax-`  | `600`       | `src/static/netsuke/assets/css/himotoshi.css`  |
| Stilyagi | `StilyagiStyle`  | `python`                                           | `stilyagi-syntax` | `--stilyagi-syntax-` | `700`       | `src/static/stilyagi/assets/styles/syntax.css` |

_Table 3: Pygments styles, the lexers each sub-site's templates actually name
in a `{% highlight %}` tag, and the generator parameters that produce each
stylesheet._

The lexer list reflects what the templates currently use, not the full set
Pygments supports; `bash`, `console`, `json`, `make`, `toml`, `powershell`, and
`xml` are stock Pygments lexers used unmodified. The bold weight differs
because the sub-sites' monospace faces read differently at the same weight:
Episodic and Netsuke stop at semibold, while Stilyagi's lighter face goes to
full bold.

### 4.7. The Weaver icon generator

`scripts/generate_weaver_icons.py` is unrelated to syntax highlighting, but
follows the same "generated, never handwritten" convention as the Pygments
generators above. It reads the checked-in mapping at
`config/weaver-icons.yaml`, which pairs each Font Awesome icon name the Weaver
sub-site used to reference with a Carbon icon identifier, pulls that icon's
path data out of the `@iconify-json/carbon` package, and writes
`templates/weaver/_icons.jinja`: a Jinja macro that inlines the SVG directly
into the page, so a published Weaver page fetches no icon assets over the
network.

```bash
uv run python scripts/generate_weaver_icons.py
```

It reports `_icons.jinja updated` or `_icons.jinja unchanged`, the same
idempotence contract as the Pygments generators. A drift test in the suite
fails if the committed macro does not match what the generator would produce
from the current mapping, so `templates/weaver/_icons.jinja` must never be
hand-edited — change `config/weaver-icons.yaml` and rerun the generator instead.

#### The shared atomic writer

`scripts/atomic_write.py` has one public function,
`atomic_write(output: Path, payload: str | bytes)`, and it is how each
single-file generator above publishes its result. Text is encoded as UTF-8;
bytes are written as given. Missing parent directories are created. The payload
goes to a unique temporary file beside `output` and is moved into place with a
same-filesystem rename, which is atomic: until the rename, `output` holds the
old contents untouched, and after it, the new contents in full — never a
partial write. The temporary file is removed on every path that does not end in
a successful rename. Failure raises `OSError`; a caller wanting a friendlier
message wraps it, as the icon generator above does, converting it to a
`SystemExit` naming the file.

`scripts/generate_weaver_icons.py`, `scripts/build_episodic_roadmap_data.py`,
and `scripts/typos_rollout_cache.py` all publish through it. The Weaver
snapshot harness's directory-level publication (`_output`, section 7.1) is a
different problem — staging and swapping a whole tree rather than replacing one
file — and is deliberately not built on this helper.

### 4.8. Weaver's chrome macros

`templates/weaver/_chrome.jinja` holds two macros shared across every Weaver
page, imported as `chrome`:

```jinja
{% import '_chrome.jinja' as chrome %}
```

`chrome.current_href(nav_links)` returns the `href` of whichever entry in
`nav_links` the page generator has flagged `current`, or `''` when none is —
which simply means no sidebar link is highlighted, the case for a page that
sits outside the nav.

`chrome.nav_link(href, index, label, current_href, variant='')` renders one
sidebar `<a>`. Every link carries the base classes
`weaver-nav-link block px-4 py-2 text-sm`. When `href` matches `current_href`,
the macro also sets `aria-current="page"`; a link that is not current gets no
`aria-current` attribute at all. It then appends one further class string,
verbatim from `_chrome.jinja`, depending on state and `variant`:

```text
current:  weaver-nav-link--current font-semibold bg-primary text-base-100 rounded-xs border border-base-content shadow-block
default:  font-medium text-base-content hover:bg-primary/5 transition-colors border border-transparent
install:  font-medium text-neutral hover:bg-accent/5 transition-colors border border-transparent font-mono
```

| Parameter      | Purpose                                                                               |
| -------------- | ------------------------------------------------------------------------------------- |
| `href`         | The link target, compared against `current_href` to decide state.                     |
| `index`        | The two-digit section number before the label, or `''` for unnumbered resource links. |
| `label`        | The link text.                                                                        |
| `current_href` | The href of the page being rendered, typically `chrome.current_href(nav_links)`.      |
| `variant`      | `'install'` selects the monospaced install-link style instead of the default.         |

_Table 4: the `nav_link` macro's parameters._

`index` also switches how the label is prefixed: a truthy `index` renders it in
a small monospaced span before the label (dimmed to 75% opacity unless the link
is current); an empty `index` on the `'install'` variant instead prefixes a bare
`>` and a space when the link is not current; any other combination prefixes
nothing. The dimming stops at 75%, not 60%: on the sidebar's cream ground,
`opacity-60` composites the ink to `#708499`, 3.33:1 against the 4.5:1 that
12px text needs, while `opacity-75` measures 4.88:1.

A typical call site, from `templates/weaver/doc_page.jinja`:

```jinja
{%- set here = chrome.current_href(nav_links) -%}
{{ chrome.nav_link('/weaver/', '00', 'Home', here) }}
{{ chrome.nav_link('/weaver/why-weaver/', '01', 'Philosophy', here) }}
{{ chrome.nav_link('/weaver/install/', '', 'Install', here, variant='install') }}
```

### 4.9. Weaver's shared page layout

`templates/weaver/doc_page.jinja` is the base layout for every Weaver page. Both
`templates/weaver/home_page.jinja` and
`templates/weaver/shared_content_page.jinja` extend it:

```jinja
{% extends "doc_page.jinja" %}
```

`doc_page.jinja` defines twelve blocks. A page that extends it inherits each
block's default content unless it overrides that block.

| Block                   | Default content                |
| ----------------------- | ------------------------------ |
| `page_title`            | empty                          |
| `extra_head`            | empty                          |
| `texture_overlay`       | texture overlay `div`          |
| `nav_subitems_how`      | empty                          |
| `nav_subitems_commands` | empty                          |
| `nav_subitems_sempai`   | empty                          |
| `nav_subitems_jacquard` | empty                          |
| `sidebar_footer`        | back-link, status dot, version |
| `main_class`            | default classes                |
| `main_extra_class`      | empty                          |
| `content`               | empty                          |
| `page_footer`           | full site footer               |

_Table 4a: every block `doc_page.jinja` defines, and what it renders by
default._

`home_page.jinja` overrides only `page_title` and `content`, and inherits every
other block — the sidebar, footer, and texture overlay on the Weaver home page
are all the base layout's defaults.

`shared_content_page.jinja` — which renders the three legal pages (privacy
policy, terms of use, code of conduct) — overrides more: `page_title` and
`content`, as above, plus `texture_overlay`, `main_class`, `sidebar_footer`, and
`page_footer`. It blanks `texture_overlay`:

```jinja
{% block texture_overlay %}{% endblock %}
```

It replaces `main_class` outright rather than extending it:

```jinja
{% block main_class %}flex-1 lg:ml-64 min-h-screen relative{% endblock %}
```

This drops `grid-bg` — the legal pages want plain ground, not ruled paper —
and, because the replacement supplies no nested block, it also drops
`main_extra_class`. A legal page that needed `main_extra_class` would have to
reinstate that nested block itself.

It shortens `sidebar_footer` to just the optional parent link:

```jinja
{% block sidebar_footer %}
            {% if parent_link %}
            <div class="p-6 border-t border-base-content/10 hidden lg:block">
                <a href="{{ parent_link.href }}" class="font-mono text-xs text-base-content/82 hover:text-accent-ink transition-colors">{{ parent_link.label }}</a>
            </div>
            {% endif %}
{% endblock %}
```

And it replaces `page_footer` with a short legal-page footer carrying the brand
line and links to the three legal pages themselves, rather than the base
layout's full site footer.

`main_class` is a sharp edge worth calling out on its own: the block is nested
inside the `<main class="...">` attribute value, not around the `<main>`
element itself —

```jinja
<main class="{% block main_class %}flex-1 lg:ml-64 grid-bg min-h-screen relative{% block main_extra_class %}{% endblock %}{% endblock %}">
```

— so overriding `main_class` replaces the whole class list rather than adding
to it. A page that wants the default classes plus one more should use
`main_extra_class` instead, which appends inside the default; only a page that
wants a genuinely different class list, as `shared_content_page.jinja` does,
should override `main_class` itself.

Table 4b lists the four blocks a page is most likely to override, with their
defaults and what overriding each is for:

| Block             | Default                                                                 | Overriding it is for                                                                    |
| ----------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `texture_overlay` | `<div class="texture-overlay"></div>`                                   | removing the paper texture, as `shared_content_page.jinja` does                         |
| `sidebar_footer`  | back-link, status dot, and version string                               | replacing the sidebar's closing content, such as with a plain parent link               |
| `main_class`      | `flex-1 lg:ml-64 grid-bg min-h-screen relative` plus `main_extra_class` | swapping the `<main>` element's class list wholesale, such as dropping `grid-bg`        |
| `page_footer`     | the full site footer                                                    | swapping in a shorter or differently structured footer, such as the legal pages' footer |

_Table 4b: the blocks a page is most likely to override._

### 4.10. Which Weaver templates use the shared layout

Twelve of the thirteen page templates under `templates/weaver/pages/` extend
`doc_page.jinja`, as do `home_page.jinja` and `shared_content_page.jinja`.
Adding a page means extending it too — the sidebar, the mobile drawer, and the
footer come with it, and a page that builds its own gets none of the fixes made
to those.

`pages/design-language.jinja` is the exception, and deliberately so. Its
sidebar is not the sub-site navigation but an in-page table of contents:
`#overview`, `#foundations`, `#typography`, `#motifs`, `#illustrations`,
`#components`. The shared layout has no block for replacing the sidebar's links
— only `sidebar_footer`, which is the panel beneath them — so a page wanting a
different set of links has to carry its own chrome. That is why the browser
suite's current-link check accepts a fragment as well as an href: on this page
the current link is `#overview`, which is correct.

The cost is real and worth stating: a change to the sidebar or the drawer has
to be made twice, once in `doc_page.jinja` and once here. Anyone touching the
chrome should grep `design-language.jinja` for the same markup.

## 5. Template components

Repeated markup belongs in a Jinja macro, and the class list behind it belongs
in the sub-site's stylesheet. These are not alternatives: a macro whose body is
a long utility string has relocated the duplication rather than removed it, and
a component class with no macro still leaves every call site restating the
wrapper element. The "Reach for the cheapest layer that works" ladder in the
"Styling" section of [AGENTS.md](../AGENTS.md) sets out when each is warranted.

`templates/episodic/components.jinja` and `templates/netsuke/components.jinja`
hold the Episodic and Netsuke sub-sites' shared macros. Import the one for the
sub-site you're editing as `ui`:

```jinja
{% extends "doc_page.jinja" %}
{% import "components.jinja" as ui %}
```

Page bodies are wrapped in `{% raw %}`, so a call has to step out of it and
back in:

```jinja
{% endraw %}{{ ui.kicker('Reference') }}{% raw %}
```

That escaping is a wart of the current template shape rather than of the macro;
narrowing the raw regions is tracked separately.

Stilyagi centralizes its chrome in `templates/stilyagi/_layout.jinja`, which
every page extends.

### 5.1. `ui.kicker`

The pill-shaped eyebrow above a page or section heading.

```jinja
{{ ui.kicker(label, extra='', accent=false, icon='', icon_class='', dot='') }}
```

| Parameter    | Purpose                                                                 |
| ------------ | ----------------------------------------------------------------------- |
| `label`      | The pill's text. Markup must be passed through `\| safe` by the caller. |
| `extra`      | Additional utility classes, in practice a margin such as `mb-6`.        |
| `accent`     | Selects the docs hub's indigo-on-boxwood-light colouring.               |
| `icon`       | An Iconify icon name, such as `carbon:download`.                        |
| `icon_class` | Utility classes for that icon, typically a colour.                      |
| `dot`        | A background utility for a leading status dot, such as `bg-amber`.      |

_Table 5: the `kicker` macro's parameters._

Three call sites show the range:

```jinja
{{ ui.kicker('Reference') }}
{{ ui.kicker('Documentation', 'mb-4', accent=true) }}
{{ ui.kicker('Current version v' ~ netsuke_version, 'mb-6', dot='bg-amber') }}
```

The presentation lives in `.hm-kicker` and its modifiers in
`src/static/netsuke/assets/css/himotoshi.css`. The base carries only what every
pill shares — `inline-flex`, centred items, the stone border, the pill radius,
size, weight, gap, and uppercasing. The face, tracking, and inset sit on the
modifiers, because the two variants differ enough that neither is a sensible
default.

| Class                 | Role                                                   |
| --------------------- | ------------------------------------------------------ |
| `.hm-kicker`          | The shared shape. Never used alone.                    |
| `.hm-kicker--hero`    | JetBrains Mono, `0.12em` tracking, translucent ground. |
| `.hm-kicker--section` | Body face, `0.05em` tracking, boxwood ground.          |
| `.hm-kicker--accent`  | Pairs with `--section` for the docs hub's indigo.      |
| `.hm-kicker__dot`     | The roadmap's leading status dot.                      |

_Table 6: the kicker component class and its modifiers._

**Normative:** a new variant is a new modifier on `.hm-kicker`, not a fresh
class list at the call site and not a utility string passed through `extra`.
`extra` is for layout that belongs to the surrounding page — a margin — not for
the pill's own appearance.

One trap to know about. `.hm-kicker--hero` sets a border colour of its own, but
it appears earlier in the stylesheet than `.hm-kicker`, which sets the `border`
shorthand. At equal specificity the later rule wins, so that declaration has
never taken effect and the hero pill's border is stone. Moving the rule would
change how the hero looks, so it has been left as it stands; do not assume the
modifier order in that file is meaningful.

### 5.2. Netsuke's page furniture: `chrome.jinja`

`templates/netsuke/chrome.jinja` holds the Netsuke page furniture that the
`doc_page.jinja` layout does not draw: the windows a code sample sits in, the
page header, and the breadcrumb. Import it as `chrome`. The homepage extends
`doc_page.jinja` like every other Netsuke content page except the standalone
`pages/icon-replacements.jinja`, so the navbar, mobile menu, and footer have
one owner; the layout's `page_scripts` block wraps the docs-only scripts and
`body_class` carries the flex column, and the homepage overrides both.

The windows are opener/closer pairs rather than `{% call %}` blocks, so a long
highlighted sample can stay inside the page's `{% raw %}` region and the calls
join the fence the `{% highlight %}` tag already needs:

```jinja
{% endraw %}{{ chrome.faux_window_open('Netsukefile') }}{% highlight 'netsuke' %}{% raw %}
netsuke_version: "1.0.0"
{% endraw %}{% endhighlight %}{{ chrome.faux_window_close() }}{% raw %}
```

`faux_window_open(label, variant='', outer_class='', frame=none, body_class=none)`
draws the dark frame, the titlebar with the traffic-light dots and a centred
`label`, and the open body element. `variant` names a modifier on
`.hm-faux-window`, in practice `card-bleed`; `outer_class` carries layout that
belongs to the page, such as a margin. `frame` and `body_class` replace the
default frame and body utilities outright and exist for the two homepage
windows that sit on their own grounds; a docs page should not need them.
`example_terminal_open(label='Terminal')` and `example_terminal_close()` are
the same shape with the tighter titlebar the example pages use.

`page_header(kicker, title, hero=false, id='', accent=false, icon='',
icon_class='', dot='')` draws the kicker pill, the `h1`, and a lede paragraph
whose text is the caller's body. The kicker options pass straight through to
`ui.kicker`. `hero=true` selects the centred hub-page treatment with the larger
heading; the default is the ruled-off docs treatment.

```jinja
{% endraw %}{% call chrome.page_header('Reference', 'CLI Commands') %}
    Build targets, inspect the plan, and control output.
{% endcall %}{% raw %}
```

`breadcrumb(trail)` takes an ordered list of mappings with a `label` and,
for every entry but the last, usually an `href`. It renders a labelled `nav`
with an `ol` and `aria-current="page"` on the final crumb. A middle entry
without an `href` renders as plain text; the example pages use one for the
category.

```jinja
{% endraw %}{{ chrome.breadcrumb([{'href': '/netsuke/docs/', 'label': 'Docs'}, {'label': 'CLI Commands'}]) }}{% raw %}
```

### 5.3. The docs sidebar: `docsnav.sidebar`

`templates/netsuke/docs_nav.jinja` holds `docs_pages`, the ordered list every
docs navigation renders from, alongside `mobile_docs_bar`, `footer_nav`, and
`docs_footer`. Each entry names the `group` heading it sits under, and
`docs_groups` fixes the heading order. `sidebar(active=none, sub_links=[],
sections=none, search=true)` draws the desktop sidebar from that list: a docs
page passes its slug and, where it has section anchors, a `sub_links` list of
`href` and `label` mappings that the macro nests under the active entry.

```jinja
{% endraw %}{{ docsnav.sidebar('cli', sub_links=[{'href': '#cli', 'label': 'Commands'}]) }}{% raw %}
```

The guides pass bespoke `sections` instead, each a mapping with a `title`, its
`links`, and `sub: true` where every link is an in-page anchor, and turn the
search widget off with `search=false`. `sidebar_link(href, label,
active=false, sub=false)` renders one entry and is what both paths call.

Adding a docs page means adding one entry to `docs_pages`; the sidebar, the
mobile dropdown, and the footer links follow. `tests/test_netsuke_navigation.py`
pins all three to the list.

### 5.4. The example pages: `exdata.example_header`

`templates/netsuke/examples_data.jinja` holds the `examples` catalogue that the
hub grid, the filter buttons, and the detail pages' "Up Next" boxes render
from. Each entry also carries the detail page header: the `level`, the
category chip's `cat_chip` variant (a modifier on `.hm-chip`), the `lede`, and
the two header `actions`, each an `href`, an `icon`, and a `label`, the first
drawn as the primary button. `example_header(key)` renders it:

```jinja
{% endraw %}{{ exdata.example_header('hello-world') }}{% raw %}
```

## 6. Browser-side components

Browser-side scripts under `src/static/netsuke/assets/js/` follow one
convention: a plain immediately invoked function expression (IIFE) module,
loaded with `<script defer>`, that guards its own initialization on
`document.readyState` (running immediately if the document has already finished
loading, or waiting for `DOMContentLoaded` otherwise). Where a component's
behaviour has a pure decision worth testing in isolation — no DOM, no timers —
that function is exported via `module.exports` at the end of the IIFE, guarded
by `typeof module !== "undefined"` so the same file still runs unmodified as a
plain browser script. `docs-scrollspy.js` exports `pickActiveIndex` (which
heading is currently being read); `config-keys.js` exports `nextTabIndex`
(which tab an arrow/Home/End keypress should move to). `mobile-nav.js` has no
such function — its logic is DOM interaction throughout — and exports nothing.

Where a module has no pure decision to extract, it is tested against a real DOM
instead. `tests/js/helpers/mobile-nav-harness.mjs` builds a happy-dom window,
injects the markup the templates render, and evaluates the shipped script into
it, so the tests drive genuine event dispatch and a genuine `activeElement`.
Both `mobile-nav.js` modules are covered this way. The choice is deliberate:
what those modules can get wrong is which element holds focus after a keypress,
and a fake DOM with hand-written focus bookkeeping would largely be testing
itself. Prefer the fake DOM used by `config-keys.test.mjs` when the behaviour
under test is a decision; reach for the harness when it is an interaction.

Underneath both approaches sits a global preload: `bunfig.toml`'s
`[test].preload` loads `tests/js/happydom.ts`, which calls
`GlobalRegistrator.register()` from the `@happy-dom/global-registrator`
development dependency. That gives every suite under `tests/js` a real global
`document`, `window`, and event machinery before a single test runs, so a
suite can assert against `document` directly without constructing one.
Suites that need an isolated window — the mobile-nav harnesses above — still
build their own `Window` rather than touching the global one; the two
coexist without interference.

The Stilyagi widgets are tested against that global document.
`tests/js/helpers/stilyagi.mjs` mounts template-faithful fixtures — one per
widget, mirroring the markup in `templates/stilyagi/pages/design.jinja`,
`docs.jinja`, and `roadmap.jinja` — into `document.body`, then evaluates the
matching widget script read straight from `src/static/stilyagi/assets/js/`,
so these suites need no build step to run. Its fixtures must stay in step
with the templates they mirror. The widgets attach listeners only inside
`body`, which the harness relies on for isolation: its `reset` clears
`document.body` and restores any patched globals — including the
controllable `IntersectionObserver` stub it installs for the docs page's
section rail — between tests. The primitives both harnesses share — evaluating
a script against a window, dispatching a click, pressing a key — live in
`tests/js/helpers/dom.mjs`.

`mobile-nav-harness.mjs` also supplies the traces both drawer suites run
over. It exports
`TRANSITIONS`, the six things that can happen to an open drawer — `toggle`,
`tab`, `shift-tab`, `escape`, `wide`, `narrow` — and
`exhaustiveTransitionSequences({ depth = 4 })`, which returns every trace over
that set up to `depth`, each one prefixed by the opening `toggle` because a
closed drawer ignores almost everything and such a trace proves nothing about
the focus trap. Traces run from two transitions long up to `depth`, and the
count is the sum of `TRANSITIONS.length ** k` for k from 1 to `depth - 1`: 258
at depth 4, 1554 at depth 5. Growth is exponential, so the depth is the budget
— each trace builds a fresh DOM.

It replaced `generatedTransitionSequences(seed, …)`, which sampled the space
randomly. For a state machine this small, the space is finite and enumerable,
and enumerating it turns the claim from "these traces held" into "no trace of
this length breaks the invariants", which is what the suites are for. It also
removes the seed, and with it the question of what the run happened not to draw.

`tests/js/mobile-nav-traces.test.mjs` tests the generator itself, because both
suites iterate whatever it returns. An empty return would leave them passing
having asserted nothing, and a loop over no items is not a failure.

The Weaver drawer suites share a harness of their own,
`tests/js/helpers/weaver-drawer.mjs`. Its `setUp` builds a happy-dom page with
the sidebar markup `templates/weaver/` renders, evaluates the shipped drawer
script into it (and `telemetry.js` too, when called with
`{ telemetry: true }`), and returns the parts a test drives — `sidebar`,
`toggle`, `backdrop`, `isOpen()`, and the recorded `events`. Because
`evaluateScript` runs shipped scripts against the process's own `globalThis`
rather than the happy-dom window's, `setUp` installs a telemetry sink there and
touches three process globals: `df12WeaverNavTelemetry`, `df12WeaverTelemetry`,
and `df12WeaverCopy`.

On a test's first `setUp` call — and only that one — the helper snapshots those
globals' prior values, so repeated `setUp` calls within one test do not
overwrite the snapshot with values the harness itself installed. The exported
`tearDown` restores them, and every file that imports `setUp` must register it
with `afterEach(tearDown)`; skip it and the sink leaks into whichever test file
the runner loads next. `tests/js/weaver-drawer-harness.test.mjs` pins this
contract with sentinel-identity tests.

Bun tests under `tests/js/` cover these pure functions, and they `require` the
**built** copy from `public/`, not the source under `src/static/`:

```javascript
const { nextTabIndex } = require("../../public/netsuke/assets/js/config-keys.js");
```

This means the copy step must have run before the suite sees a source change, so
`make test-js` runs `bun run build:static` before `bun run test:js`. Driving
`bun test tests/js` directly skips that, and will quietly test the previous
form of anything edited since the last build. (`make build` does not cover it:
that target builds the Python virtual environment, not the site.)

Nothing here is bundled, transpiled, or module-loaded: `scripts/copy-static.ts`
copies these files verbatim. There are no ES modules, no classes, and no custom
elements anywhere on the site at the time of writing. Encapsulation is the IIFE
and nothing else, with the DOM contract expressed through `data-*` attributes
so that restyling cannot break a selector, and an early return when the root
element is absent so one `defer` script can be loaded on pages that do not use
it — `doc-search.js` is included on thirteen pages this way.

`src/static/episodic/assets/js/site-search.js` follows the same plain-script
shape. It exposes seven helpers when `module.exports` is available:
`createIndexCache` for shared in-flight index loads, `fetchEpisodicSearchIndex`
for fetching and deserializing the MiniSearch payload, `searchEpisodicIndex`
for query-time ranking, `initialiseEpisodicSearch` for one root,
`initialiseAllEpisodicSearch` for the document, `durationBucket` for the fixed
telemetry duration classes, and `emitSearchTelemetry` for its bounded event
schema. The initializers accept injected loader, search, and navigation
dependencies so their DOM behaviour can be tested without a network request or
navigation. Their roots must provide the `data-search-root`,
`data-search-index`, `data-search-input`, `data-search-panel`,
`data-search-results`, and `data-search-meta` contract. The search helpers are
written so the loading boundary stays outside the query path: queries only
consult an already-loaded index, while initialization owns the fetch and
failure handling. Failed cache entries are evicted, allowing a later root
initialization to retry.

### 6.1. Episodic search telemetry

Search-index observability is optional and privacy-preserving. A production
host may set `window.df12EpisodicSearchTelemetry` to a function before the
deferred search script loads; without that function, telemetry is a no-op. The
sink receives only fixed labels: `operation` (`episodic-search-index`),
`outcome` (`requested`, `success`, `failure`, or `evicted`), `cache_state`
(`hit`, `miss`, or `evicted`), `attempt` (`initial` or `retry`), and, for load
outcomes, a bounded `duration_bucket`. It therefore records cache hits and
misses, load outcomes, failure eviction, retry outcomes, and coarse duration
without transmitting search queries, document text, paths, URLs, or persistent
identifiers. A telemetry sink must treat the event as operational metadata only
and must not enrich it with page or user data.

An element may still carry an id for the stylesheet or for an ARIA
relationship; what the convention rules out is _script_ depending on one. The
Netsuke navbar is the worked example: `#navbar` and `#navbar-mobile-menu` are
load-bearing for `himotoshi.css` and for the toggle's `aria-controls`, so they
stay, while `mobile-nav.js` addresses the same elements as `[data-mobile-nav]`,
`[data-mobile-nav-toggle]`, and `[data-mobile-nav-menu]`. The toggle and menu
are resolved within the root rather than from the document, so the root is the
only thing a page has to get right.

The convention's limits are worth naming because they decide when to leave it.
A module is a file plus a `data-` prefix, so nothing enforces one instance per
root, nothing provides a lifecycle beyond first run, and nothing tells CSS that
a script has upgraded the markup — `config-keys.js` has to add an `is-enhanced`
class by hand for that. When a behaviour outgrows those limits, the next step
is a custom element in the light DOM, which supplies all three: one instance
per root, `connectedCallback`, and `:defined`. See the ladder in the "Styling"
section of [AGENTS.md](../AGENTS.md); a custom element is its last rung, and
the site does not use a front-end framework at all.

### 6.2. The Weaver mobile drawer

`src/static/weaver/assets/js/mobile-nav.js` turns the sidebar into a drawer
below the tablet breakpoint. It builds its own controls rather than expecting
them in the markup, so a page supplies three hooks and gets the rest.

**What a page must provide.** The script returns early — silently, leaving the
page exactly as it was — unless it finds all three:

| Hook                       | What it is                                  |
| -------------------------- | ------------------------------------------- |
| `#sidebar`                 | the element that becomes the drawer         |
| a `nav` inside it          | the links; given `id="sidebar-nav"` if bare |
| `[data-mobile-nav-header]` | where the toggle is placed                  |

The early return is why `shared_content_page.jinja` had to grow the header
hook: the legal pages had a sidebar and a nav but no header, so they shipped
without mobile navigation at all and nothing said so.

**What the script adds.** A `button#mobile-nav-toggle` inside the header and a
`div#mobile-nav-backdrop` after the sidebar. The button carries no markup of
its own: it wears `.weaver-brand-mark`, which supplies the indigo block, the
glyph, and the centring from `src/styles/weaver/chrome.css`. Its accessible
name is an `aria-label` that changes with its state, and `aria-controls` points
at the nav's id.

**The two classes that drive the CSS.** `has-mobile-nav` goes on `<html>` as
soon as the script runs, and is what lets the stylesheet hide the nav — without
it a reader with JavaScript disabled would be left with a navigation nothing
can open. `mobile-nav-open` goes on `#sidebar` while the drawer is open, and is
the selector for both the drawer itself (`#sidebar.mobile-nav-open nav`, which
is `display: block; position: fixed`) and the backdrop
(`#sidebar.mobile-nav-open ~ #mobile-nav-backdrop`).

**One breakpoint, written twice.** The stylesheet's drawer rules sit in
`@media (max-width: 1023px)`; the script watches
`matchMedia("(min-width: 1024px)")` and closes the drawer when that starts
matching, so the page is never left scroll-locked behind a drawer that the
layout has just hidden. The two are the same boundary and have to move together.

**Scroll locking is vertical only.** Opening the drawer saves
`document.body.style.overflowY` and sets it to `hidden`; closing restores what
was saved. It must be `overflowY` and not `overflow`: the body already carries
`overflow-x: hidden` from a class, and setting both inline replaces that
declaration for as long as the drawer is open, letting the page jump sideways.
Because the computed value is the same either way, only the inline declaration
distinguishes them — which is what `tests/test_weaver_browser_interaction.py`
asserts.

**Focus.** Opening saves `document.activeElement` and moves focus to the first
focusable element in the nav, or to the nav itself if it has none. A `keydown`
handler traps `Tab` inside the drawer while it is open. Closing restores the
saved element — unless it was `<body>`, is no longer connected, or cannot take
focus, in which case focus goes to the toggle. `<body>` is the common case:
someone who opened the drawer by tapping it had nothing focused, and returning
focus to `<body>` would strand it on a hidden nav link.

**Four ways to close**, each reported with its own telemetry reason: the
toggle, the backdrop, any link in the nav, and `Escape`. The breakpoint
crossing is a fifth, and is the one a reader does not initiate.

### 6.3. Weaver chrome telemetry

The Weaver drawer and its copy controls report through the same optional hook
model as Episodic search. A production host may set
`window.df12WeaverNavTelemetry` to a function before the deferred scripts run;
without it, `src/static/weaver/assets/js/telemetry.js` is a no-op and nothing
is collected. A sink that throws is caught and ignored because observability
must not be able to break the drawer or the button it was watching.

Every event has the same shape, and the whole of what may leave the page is
declared as three frozen vocabularies at the top of that file:

| Field       | Values                                                                                                                  |
| ----------- | ----------------------------------------------------------------------------------------------------------------------- |
| `component` | `weaver-mobile-nav`, `weaver-copy-button`                                                                               |
| `operation` | `drawer`, `clipboard`                                                                                                   |
| `outcome`   | `initialized`, `opened`, `closed`, `focus-restored`, `copied`, `failed`                                                 |
| `reason`    | `toggle`, `backdrop`, `nav-link`, `escape`, `breakpoint`, `saved-element`, `toggle-fallback`, `unavailable`, `rejected` |

_Table 7: every field a Weaver chrome telemetry event may carry._

`reason` is present only where an outcome has more than one cause worth
separating: which of the five things closed the drawer, whether focus went back
to where it came from or fell back to the toggle, and whether a clipboard write
found no API or was refused one. An `operation`, `outcome` or `reason` outside
those lists is dropped rather than emitted, so the table is the schema rather
than a description of it.

What it therefore records is that a drawer was built, opened, and closed for a
stated cause; where focus went afterwards; and whether a copy succeeded. What
it cannot record — because there is nowhere in the schema to put it — is a URL,
a page path, a navigation label, the copied text, or anything identifying a
person or persisting between visits. A sink must treat the event as operational
metadata and must not enrich it with page or user data.

**The inspection point for a maintainer is
`src/static/weaver/assets/js/telemetry.js`.** It is about a hundred lines, the
vocabularies are the first thing in it, and `emit` is the only function that
calls the sink. Reading those two things is the whole of the privacy argument;
`tests/js/weaver-telemetry.test.mjs` is the enforcement, and it tries to get
page data, clipboard contents and identifiers into an event rather than only
checking the happy path.

The copy controls need a seam because they are inline `onclick` handlers in the
templates. They call `df12WeaverCopy('…')`, which writes to the clipboard and
reports the outcome; the text is passed to the clipboard and never to the sink.
`telemetry.js` is loaded before `mobile-nav.js` and defines the API
unconditionally, because `mobile-nav.js` returns early on a page without the
drawer's markup while the install page's copy buttons still need it.

### 6.4. The config-keys component

`config-keys.js` drives the "config keys" browser on the configuration docs page
(`templates/netsuke/pages/docs-configuration.jinja`), which pairs each key
group's label with an always-present code extract.

**DOM contract.** A container carries `data-config-keys`. Inside it:

- `[data-config-keys-labels]` wraps one `[data-config-keys-key]` per group,
  each holding a `[data-config-keys-label]` (the group's heading) and
  optionally a `[data-config-keys-note]` (a paragraph describing the group).
- `[data-config-keys-panels]` wraps one `[data-config-keys-panel]` per group,
  in the same order as the keys. The component requires a `panels` list, a
  `labels` list, and an equal, non-zero count of keys and panels; it does
  nothing otherwise (`initGroup` returns early).
- Every panel carries `tabindex="0"` in the template markup, independent of
  which mode is active, so it stays reachable by keyboard as a scroll container
  even before JavaScript runs — a scrollable region that cannot be focused
  cannot be scrolled by keyboard at all.

**No-script fallback.** Without JavaScript, every panel is visible, labelled by
its heading (`aria-labelledby`) and described by its note (`role="group"` on
each panel in the template markup). This is three labelled, described listings,
nothing hidden — the safe degraded state the script only ever narrows from.

**Normative:** any style that assumes the script has run must be gated on the
`is-enhanced` class, which `initGroup` adds to the `[data-config-keys]`
container only after `applyMode` has rearranged the DOM. The narrow tab strip
is the case in point. It lays the key groups out abreast, which is right only
once the script has moved each note out of its group and above the panel;
ungated, it applied on viewport width alone and squeezed three untouched groups
— heading plus a full sentence of prose each — into one strip, wrecking the
very fallback described above. A media query alone cannot know whether the DOM
it is styling has been enhanced; the class is what tells it.

**Two modes and the breakpoint.** `config-keys.js` watches
`window.matchMedia("(min-width: 768px)")` and switches behaviour on change:

- **Wide** (≥768px): every panel stays visible, matching the no-script
  layout. Labels are plain `<span>` elements — inert text, not controls —
  because there is nothing to reveal and nothing to operate: pointing at either
  half of a key/panel pair (`pointerenter`/`pointerleave`) marks both with a
  preview class, and that is the only interaction. `applyWide` restores
  `role="group"` on each panel and removes the `aria-describedby` the narrow
  mode adds.
- **Narrow** (<768px): there is no room for every listing, so only the
  selected panel is shown (`hidden` toggled on the rest) and each label becomes
  a `<button>` in a `role="tablist"`, with full APG tab semantics — arrow keys
  and Home/End move selection (`nextTabIndex`), `aria-selected` and roving
  `tabindex` track the active tab, and `applyNarrow` sets `role="tabpanel"` on
  the panel and moves the group's note above the panel, associating it via
  `aria-describedby`.

The labels really are `<span>`s in one mode and `<button>`s in the other, and
the ARIA genuinely differs between modes, rather than a fixed `role="tab"`
markup that is merely styled differently: a control that does nothing is worse
than no control, and a tab whose panel is always visible is a lie to a screen
reader, so neither is declared unless the layout has actually made it true.
`applyMode` runs on load and on every breakpoint crossing (`change` event on the
`MediaQueryList`, with the legacy `addListener` fallback `mobile-nav.js` also
uses), swapping the DOM node, role, and attributes each time.

**Building a second component the same way.** Follow the same shape: a
container with a stable `data-*` hook, sub-elements addressed by their own
`data-*` attributes rather than classes (so styling changes never break the
selector), a no-script markup state that is fully usable on its own, an
`is-enhanced`-style class gating any CSS that depends on the script having
rearranged that markup, a pure decision function factored out for anything with
branching logic worth testing directly, `module.exports` guarded for Bun, and a
`matchMedia` listener — with the pre-`addEventListener` fallback — for any
behaviour that genuinely differs by viewport width rather than merely being
restyled by it.

## 7. Styling and the cascade

The Netsuke sub-site still loads the
[Tailwind Play CDN](https://tailwindcss.com) script
(`<script src="https://cdn.tailwindcss.com">`) rather than a compiled
stylesheet, and uses its utilities in its markup alongside its own hand-crafted
stylesheet; it extends the default theme through
`/netsuke/assets/js/tailwind-config.js`. This differs from the main site,
mxd, Weaver, and Stilyagi, which compile Tailwind v4 ahead of time; see the
[Tailwind v4 guide](tailwind-v4-guide.md) for that path. Stilyagi's only
remaining hand-crafted stylesheet is the generated Pygments block at
`src/static/stilyagi/assets/styles/syntax.css`, and even that is `@import`ed
into `src/styles/stilyagi.css` rather than linked on its own.

Weaver was in Netsuke's position until recently, and moving it off the Play CDN
is the worked example of what that migration costs. The doubled-selector idiom
below exists because the CDN's injected `<style>` is unlayered; the compiled
build has no such tie to break, because its utilities sit in `@layer utilities`
and a sub-site's own rules sit in `@layer components`, where they lose to a
utility by construction rather than by source order. The inversion is the trap:
a handwritten stylesheet that was _left_ unlayered under the compiled build
stops losing those arguments and starts winning them, silently. See
`src/styles/weaver.css` for the arrangement and
`docs/execplans/weaver-daisy-migration.md` for what the change turned up.

The Play CDN script scans the rendered document for utility classes in use and
injects the utilities it finds into a `<style>` element it appends to
`<head>` — after the handwritten stylesheet `<link>`, regardless of where the
`<script>` tag itself sits in the markup. Because that injected `<style>` is
unlayered, and Tailwind's Play build carries no `@layer` boundaries the way the
compiled entrypoints do, an unlayered handwritten rule of _equal_ specificity
loses: CSS resolves a tie in specificity by source order, and the CDN's
injected block comes later.

The idiom used to win instead is to double the selector, raising its
specificity above a single utility class without touching source order:

```css
/* On narrow viewports the vertically centred hero content rides up under the
   fixed navbar. Floor the hero's top padding so the kicker never sits closer
   than 92.2px to the top of the viewport. The selector is doubled to outrank
   the hero's `py-16` utility, which the Tailwind Play CDN injects into a
   later <style> block at equal specificity. */
@media (max-width: 499.98px) {
  .hm-hero.hm-hero {
    padding-top: 92.25px;
  }
}
```

(`src/static/netsuke/assets/css/himotoshi.css`). The same idiom recurs wherever
a handwritten rule must outrank a Tailwind utility of the same class count on
this sub-site, for example
`section .hm-faux-window--card-bleed.hm-faux-window--card-bleed` a little
further down the same file. Prefer raising specificity by doubling the class
over `!important`, which would also outrank a later, deliberate override.

### 7.1. Verifying a styling change against Weaver

`scripts/weaver_snapshot.py` is the command surface; the work sits in ten
siblings beside it, none over 400 lines, named for what they do: `_paths` (the
published tree, the page list, and each page's filename stem), `_locking`
(advisory locks and lock-file hygiene), `_output` (staging and failure-atomic
publication), `_ownership` (proving whose server answered), `_serving` (ports,
the server, and its lifecycle), `_tools` (the argv handed to css-view and
agent-browser), `_colour` (one colour written one way), `_normalize` (reducing
a captured tree to what a reader could see), `_clock` (the passage of time, as
something a caller can supply), and `_process` (starting, polling, and stopping
the server child). They are plain modules rather than a package, so a script
run by path finds them on `sys.path` and the invocation below is unchanged.

Every outward dependency the harness has — the clock, the readiness probe, the
process launcher, the marker fetch, the file mover, the port allocator — is a
parameter with a production default, bound at the function that needs it. A
caller that does not care never sees the parameter; a test supplies a stand-in
and so exercises retry pacing, timeout escalation, and failure paths without a
real sleep, socket, or child process.

`_clock` names that pattern for time specifically: a `Clock` protocol with
`monotonic` and `sleep`, and `SYSTEM_CLOCK`, the real one, which is what
production always uses. The lock's timeout and the server's readiness poll are
both loops over a clock rather than over `time` directly, so a test can check
how many attempts are made and how long is waited between them without sitting
through it.

`_process` is the half of serving that is about the child rather than the port:
the `Probe` and `Launcher` types, with `_probe_url` and `_launch` as their
production defaults, a readiness poll (`_await_server`) that tries fifty times
at 0.2 seconds apart — roughly ten seconds — before giving up, and a shutdown
(`_stop`) that asks the process to terminate and, if it has not gone within a
ten-second wait, kills it and waits up to ten seconds more. Both loopback
requests it makes — the readiness probe and, via `_ownership`, the marker fetch
— go through an opener that refuses HTTP redirects (`_RefuseRedirects`, built
into `_NO_REDIRECTS`): every request here is to the server this run just
started, so a redirect is not a route to follow but proof that whatever
answered is not that server, and the run should fail rather than trust content
from wherever the redirect points.

The `Launcher` type returns a `ServerProcess`, and `_start_server` (in
`scripts/weaver_snapshot_serving.py`) hands one back to its caller. The
protocol names the union of what serving consumes from the child: `poll`
(from `_Pollable`) and `terminate`, `kill`, and `wait` (from `_Stoppable`).

The startup lock in `scripts/weaver_snapshot_serving.py`'s `_start_server`
covers exactly the probe, the spawn, and the wait for readiness; it is released
before the ownership check that confirms the server answering is this run's,
which stops the server and fails the run if that confirmation does not come
back.

`scripts/weaver_snapshot.py` exists because a cascade change on a compiled
Tailwind sheet is easy to get subtly wrong: nothing errors, a selector simply
stops matching what it used to, and the only symptom is an element that has
quietly moved, resized, or changed colour somewhere the change was not meant to
reach. The harness answers that by recording every Weaver page's computed
styles before and after a change and diffing the two, rather than relying on a
reviewer noticing a drift by eye.

Three things about how it runs are worth knowing before reading its output.

The server binds loopback only. `http-server` defaults its address to
`0.0.0.0`, which would offer the published tree to every host that can reach
the machine for as long as a capture runs; `_server_argv` passes `-a 127.0.0.1`
instead.

The port defaults to `0`, meaning the kernel picks a free one, so two runs in
two worktrees do not contend. Pass `--port` only to reach the served tree from
a browser by hand. Where a port is named explicitly, a lock keyed on it
serializes the probe-and-spawn window, and the run proves the server answering
is its own by fetching back a marker file it placed under `public/` — once when
the server comes up and again when the capture finishes.

Output is published rather than written in place. A capture goes to a private
staging directory and is moved into the destination only once every page has
succeeded, under a lock keyed on that destination; `diff` takes the same lock
while reading. So a run that fails partway leaves the previous results
untouched, two runs writing one directory do not interleave, and a diff never
observes a directory halfway through being replaced. Publication clears only
the extension being written, so a `capture` and a `shots` run can share a
directory.

An ordinary publication failure rolls the destination back to the previous
run's results, removes the staging directory, and exits naming the
destination. If the rollback itself fails or is interrupted — a second
Ctrl-C landing between two restores, say — the destination may be left
holding neither run's results in full; the run then raises the documented
inconsistent-destination error, keeps the staging directory, and says so.
That directory's `replaced/` subdirectory holds the only surviving copy of
the previous run's files, so it must not be deleted by hand without
recovering them first.

It is a cyclopts app with three subcommands, invoked bare — there is no
Makefile target and no console-script entry point:

```bash
uv run python scripts/weaver_snapshot.py capture <out-dir>
uv run python scripts/weaver_snapshot.py shots <out-dir>
uv run python scripts/weaver_snapshot.py diff <before> <after>
```

`capture` serves `public/` and records every published Weaver page's computed
styles as JSON, via `bun x css-view --mode walker`. `shots` screenshots each
page at 360, 768, and 1440 CSS pixels with `agent-browser`, for the cases a
style diff cannot catch on its own — a wrong icon glyph, a texture that failed
to load. `diff` normalizes both snapshot trees and prints a unified diff per
page, exiting non-zero when any page differs; that exit status is what makes it
usable as a gate rather than merely informative.

The typical loop is to capture a baseline before touching anything, make the
change, capture again, and diff the two directories. An empty diff confirms the
change moved nothing it was not meant to; a non-empty one should be read entry
by entry, since every difference ought to trace back to something the change
deliberately did.

### 7.2. Property-based tests for the snapshot normalizer

`tests/test_weaver_snapshot_properties.py` complements the example-based
`tests/test_weaver_snapshot_*.py` suites with
[Hypothesis](https://hypothesis.readthedocs.io/) (`hypothesis` is a `dev`
dependency-group entry in `pyproject.toml`). Rather than asserting what the
normalizer in `scripts/weaver_snapshot_normalize.py` does to worked-example
inputs, it asserts invariants that must hold for every input Hypothesis can
generate — colour notations, style-diff shapes, and walker trees nobody thought
to write by hand.

Four families of property are checked:

- **Idempotence.** Normalizing an already-normalized colour, shadow, or
  walker tree changes nothing, since a snapshot is only ever compared against
  another snapshot.
- **Structure preservation.** Normalizing a walker tree never adds, drops,
  or reorders a node; only the incidental values within it change.
- **Totality of removal.** Every `--tw-*` custom property is stripped from a
  style diff, and no transparent shadow layer survives normalization, whatever
  else the value contains.
- **Injectivity of the slug.** No two distinct page paths produce the same
  snapshot filename stem, since one capture would otherwise overwrite another
  and the diff would compare a page against itself. The generated alphabet
  includes `_`, which is what makes the property able to reach the collision at
  all: the stem uses `__` as its separator.

Every test shares a module-level `SETTINGS` object, applied via `@SETTINGS`
beside each `@given`. It pins `max_examples=200` and sets `deadline=None`, and
it suppresses Hypothesis's `too_slow` and `data_too_large` health checks. This
suite runs inside the commit gate (`make test`), where a health check flagging
one slow-but-valid example, or an unpinned example count happening to pick a
different case on a different run, would fail the gate on a finding rather than
a genuine defect.

Run just this file:

```bash
uv run pytest tests/test_weaver_snapshot_properties.py -v
```

### 7.3. Browser-driven checks against the served pages

`tests/test_weaver_browser.py` and `tests/test_weaver_browser_interaction.py`
are the two Weaver suites that watch a real Chromium rather than reading text.
The former checks what every published page looks like once it has loaded; the
latter checks what happens when something acts on one — a copy-button click, a
resize past the mobile breakpoint, the drawer opening, the `capture` command
run end to end. The build tests read the delivered markup and the compiled
stylesheet as strings, and the snapshot tests exercise the harness that drives
a browser without ever starting one; these two suites serve `public/` and drive
`agent-browser` over it, so they can observe served responses, composited
colours, and the laid-out result rather than the markup that describes them —
whether a declared stylesheet actually 404s, what a translucent panel's colour
composites to once the cascade has had its say, and whether the sidebar
genuinely gives way to the drawer at a narrow viewport.

Both carry the `playwright` marker, so `uv run pytest -m "not playwright"`
deselects them while iterating on something else. Both also degrade to a skip
rather than a failure when a dependency is absent: `agent-browser` not on
`PATH`, `node_modules/.bin/http-server` missing (run `bun install`), or `uv` or
`bun` themselves not on `PATH`.

`built_site`, `served`, and `drive` are session-scoped fixtures in
`tests/conftest.py`, shared with the build suites and between the two browser
suites, so `bun run build` runs once for all of them rather than once per
module. The page list, the viewports, the axe waivers, and the helpers that
read state back out of the browser — the request log, axe's report, the result
of an evaluated expression — live in `tests/support/weaver_browser.py`, so both
suites drive the browser the same way over the same matrix.

**The matrix.** The page list is derived from `config/pages.yaml` — the same
file the generator itself reads — rather than hard-coded or drawn from the
published tree, so all seventeen published pages are covered, and a page added
to the config is covered automatically, without anyone remembering to add it
here. The config has to be read this way because parametrization happens at
collection, before the session-scoped `built_site` fixture has built anything;
a companion test,
`test_the_published_tree_holds_exactly_the_pages_checked_here`, asserts that
the config and the published tree agree, so a config that has drifted from the
build fails loudly rather than leaving a page silently unchecked. Most tests
run at two viewports: 360×800, the narrowest width the design targets and the
one that puts the sidebar off-canvas behind a toggle, and 1440×900, the width
the layout was drawn against. The two layouts share almost no chrome, so both
have to be checked.

**What `test_weaver_browser.py` asserts, per page:**

- `test_a_weaver_page_is_self_contained` — every request the page makes comes
  from the local origin and none fails, and the page actually fetched a
  stylesheet, a font, and a script, so the first half of that check cannot pass
  vacuously on a page that fetched nothing.
- `test_a_weaver_page_meets_wcag_aa` — axe reports no unwaived violation
  against WCAG 2.0 A and AA.
- `test_a_weaver_page_renders_its_chrome` — the current-link and icon
  contracts described below.
- `test_a_weaver_page_fits_a_phone` — at 360px the drawer toggle is present,
  the sidebar does not lay out, and the document's scroll width does not exceed
  the viewport.
- `test_a_weaver_page_lays_out_its_sidebar_on_a_desktop` — the sidebar lays
  out at 1440px, the wide layout's half of the same swap.

Two further tests in this file are not parametrized per page:

- `test_the_recorded_contrast_exceptions_are_still_real` — the two waived
  `safety/` labels still fail exactly as recorded (see below).
- `test_the_published_tree_holds_exactly_the_pages_checked_here` — the
  companion test named above: the published tree and `config/pages.yaml` name
  exactly the same pages.

**The current-link contract.** At most one sidebar link may carry
`aria-current="page"`, and where one does, it has to point at somewhere the
page actually is. Three shapes are legitimate: the page's own href; an ancestor
of it, since the three command sub-pages highlight the Commands section they
belong to; and a fragment, since the design-language page reuses the nav
classes for its own in-page anchors. A page the sidebar does not list — the
three legal pages — has no current link at all, which is also correct: the
chrome macro returns an empty string for them rather than guessing.

**The icon check.** Every rendered `<svg>` must have a body, and no page may
contain the literal text `UNKNOWN ICON`. The count of icons on a page is only
asserted to be non-zero outside `SHARED_CONTENT`, since the three legal pages
carry the sub-site's chrome but no illustration of their own.

**The `ACCEPTED` waiver.** `pages/safety.jinja`'s Operational Guidance panel
carries two status-token labels whose measured contrast is a recorded,
outstanding defect rather than something this suite is meant to catch fresh
each run (see the Decision Log in `docs/execplans/weaver-daisy-migration.md`).
`ACCEPTED` waives exactly those two: it is keyed by page, axe rule, and the CSS
class carried on the failing node, so it excuses the `text-status-ok` and
`text-status-error` labels on `safety/` and nothing else — a contrast failure
anywhere else on the same page still fails the suite.
`test_the_recorded_contrast_exceptions_are_still_real` asserts the two waived
labels still fire; if a future palette change makes them pass, that test fails
instead, so the waiver cannot quietly outlive the defect it was recorded
against.

**What `test_weaver_browser_interaction.py` asserts:**

- `test_a_copy_control_hands_the_clipboard_what_it_shows` — the home page's
  install-command button, and the install page's unlabelled buttons, hand a
  stubbed `navigator.clipboard` exactly the text each sits beside.
- `test_a_long_code_line_scrolls_its_panel_and_not_the_page` — on `docs/`,
  `commands/act/`, and `sempai/`, a three-hundred-character line injected into
  a code panel either wraps or scrolls that panel, and never widens the
  document itself.
- `test_the_capture_command_writes_one_snapshot_per_page` — runs
  `scripts/weaver_snapshot.py capture` end to end and checks it writes one
  non-empty snapshot per published page.
- `test_the_drawer_opens_on_a_published_page` — on `privacy-policy/` and the
  home page, opening the drawer sets its ARIA state, shows the backdrop, moves
  focus inside it, and locks the body's vertical scroll without touching the
  horizontal.
- `test_a_copy_control_reports_its_outcome_and_not_its_contents` — the copy
  telemetry event carries only the fixed `component`/`operation`/`outcome`
  schema, never the copied text or anything identifying the page.

Run either file on its own:

```bash
uv run pytest tests/test_weaver_browser.py -v
uv run pytest tests/test_weaver_browser_interaction.py -v
```

Together they cover every published page at two viewports for the
self-containment, accessibility, chrome, and layout checks, plus the smaller,
non-parametrized batteries described above — 121 cases in the page-level suite
and 9 in the interaction one. Expect the pair to take between three and four
minutes including the build, most of it in the page-level suite, since axe runs
once per page per viewport.

### 7.4. Mobile overflow below the tablet breakpoint

`src/styles/weaver/site-base.css` carries a `@media (max-width: 767px)` block
that lets certain content break mid-token, and headings hyphenate, rather than
let the document scroll sideways. Below the breakpoint, `pre`, `code`, `th`,
`td`, and `.font-mono` get `overflow-wrap: anywhere`; `h1`–`h4` get
`overflow-wrap: break-word` together with `hyphens: auto`.

It exists because four pages laid the document out wider than the 360px viewport
`tests/test_weaver_browser.py` checks against. Their measured widths were
`sempai` at 826px, `jacquard` at 416px, `install` at 370px, and `docs` at
376px. There were two causes, both of them content that cannot break at a
space. A command line, a TOML key, or a table cell holding a path sets a
minimum width its column cannot meet. A display heading has the same problem
for a different reason: "Documentation" at `text-5xl` is 344px on its own,
against a 296px column.

The rule is deliberately scoped below the tablet breakpoint, so the wide layout
— where nothing overflows and a mid-token break would be gratuitous — is
untouched.

### 7.5. Validating rendered pages in a browser

The commit gates do not render the site, so a change to a template, a
stylesheet, or `config/pages.yaml` is checked in a real browser before it is
committed. The normative procedure is
[Validating rendered pages](../AGENTS.md#validating-rendered-pages) in
`AGENTS.md`; this section explains the tools it relies on and why each step is
there.

Two command-line tools do the work, and neither needs a display. `agent-browser`
drives a headless Chromium: it opens a page, waits for `networkidle`, takes a
full-page screenshot, lists the accessibility tree with element refs, resizes
the viewport with `agent-browser set viewport <w> <h>`, and evaluates
JavaScript against the page. `css-view` captures every element's computed
styles and bounding box as JSON, which `jq` can then query or `diff` can
compare. Both have a skill under the agent's skills directory that carries the
current command reference; load it rather than working from memory.

The dev server is the target. `bun run dev` watches `src/`, `df12_pages/`,
`config/`, `scripts/`, and `pyproject.toml` and rebuilds on change; `bun run
serve` builds once. Both honour `DF12_PORT`, so several worktrees can be served
at once. Confirm the server answers with `curl` before driving it, and stop it
afterwards.

Four checks follow, and the second is mandatory for every changed page rather
than a spot check:

1. **Read the screenshot.** A rendering that passes every gate can still be
   wrong on the page, and the screenshot is the only check that sees it.
2. **Audit every supported viewport for horizontal overflow.** The site
   supports widths from 320px upwards and the Tailwind breakpoints move the
   layout at 640, 768, 1024, and 1280px, so each changed page is checked at
   1440, 1280, 1024, 768, 390, and 320px. At each width,
   `document.documentElement.scrollWidth` must not exceed
   `document.documentElement.clientWidth`; `clientWidth` is used rather than
   `window.innerWidth` because it excludes the vertical scrollbar. The usual
   cause of a failure is a code block or table inside a grid or flex column:
   the fix is `overflow-x-auto` on the wide content and `min-w-0` on the
   column, never a clip on the page. Section 7.4 records how the same
   failure was found and fixed on Weaver.
3. **Inspect computed styles when a screenshot cannot settle the question.**
   `css-view` shows the value a utility resolved to, whether a theme token
   propagated, and whether an element that should be hidden has a zero-height
   box.
4. **Diff before and after for output-neutral changes.** A refactor that is
   meant to change nothing visible — moving utilities into a component class,
   extracting a macro, reorganizing a stylesheet, upgrading a dependency — is
   proven by capturing `css-view` snapshots before and after at the same
   viewport and diffing each node's tag, computed styles, and bounding box.
   Class attributes are left out of the projection on purpose, since
   renaming classes is usually the point. An empty diff is the evidence; a
   non-empty diff is either a bug or a change the commit message must
   describe.

Finish with the accessibility audit in section 8.

## 8. Accessibility checks

Colour choices must meet WCAG 2.2 AA — 4.5:1 for body text, 3:1 for large text
and non-text elements such as icons and borders — per
[Accessibility](../AGENTS.md#accessibility) in `AGENTS.md`. Spot-check affected
pages with an accessibility (a11y) audit tool at both a narrow and a wide
viewport after any change to colour or markup structure, since a pairing that
passes at one breakpoint's layout is not guaranteed to pass at another's.

A colour pairing that fails is not automatically a regression introduced by the
change under review: this repository's execution plans record contrast risks
that were caught and fixed before shipping — for example
`--netsuke-indigo-light` directly on the charcoal background, roughly 2.1:1 and
well below the 4.5:1 floor, which is why the Netsuke syntax-highlighting
palette instead uses the dedicated, separately validated `--netsuke-syntax-*`
variables (see the
[Netsuke update execution plan](execplans/netsuke-update.md)). No outstanding,
unaddressed colour-contrast finding is recorded in this repository's
documentation at the time of writing; this guide could not verify a specific
list of known pre-existing findings from an accessibility (a11y) tooling
report, and none is checked into the repository. Before treating a new audit
finding as a regression, check the change under review actually altered the
colour or markup in question, since an audit run against a wider page surface
than the change touched can surface pairings the change did not introduce.

The Weaver sub-site's pages are additionally checked with axe over WCAG 2.0 A
and AA by the browser suite; see §7.3, "Browser-driven checks against the
served pages".

### 8.1. Focus indicators

An audit tool will not catch a missing or invisible focus ring: it inspects the
resting page, and a ring only exists while a control is focused by keyboard.
Two things have removed one on this site, and neither showed up in an axe run.

A control's colour tokens follow the ground its _contents_ sit on; a focus ring
follows the ground it is _painted_ on, and the two are not the same surface.
Stilyagi's ring sits at a positive `outline-offset`, so it is painted on the
page around a control rather than on the control's own fill: an ink-filled chip
on a paper bar still needs the ink ring, because that is what its ring lands
on. Only a ring drawn at a negative offset, over the control's own dark ground,
takes the paper colour — which is why the three scrollers that do so declare it
beside the offset rather than inheriting it from the dark-surface block.

`tests/test_stilyagi_focus.py` holds that rule as a test: any rule granting a
paper ring must also draw it inside its control. It runs without a browser. The
same module carries a Playwright check that measures the ring on the active
RsDoc filter chip — the sharp case, an ink fill on a paper bar, above the
1280px breakpoint where the chip row is the control. Playwright is not a
dependency here, so that check skips unless it is installed:

```bash
bun add -d playwright
bun x playwright install chromium
uv run pytest tests/test_stilyagi_focus.py -v
```
