# Developer's guide

This guide is for maintainers and contributors working on the df12 Productions
website generator, its sub-site templates, stylesheets, and browser-side
scripts. It covers how to build and serve the site locally, how generated and
hand-crafted files are separated, how the Pygments syntax highlighting for the
Netsuke and Stilyagi sub-sites is generated, the shared Jinja macros and the
component classes they pair with, the convention used for browser-side
components, the cascade quirks introduced by the Netsuke and Weaver sub-sites'
use of the Tailwind Play content delivery network (CDN), and how accessibility
is checked. It does not restate deployment or OpenTofu guidance, which lives in
[`AGENTS.md`](../AGENTS.md).

For the shape of the repository, see [Repository layout](repository-layout.md).
For the generator's architecture and extension points, see
[df12 Pages App Design](df12-pages-app-design.md). For Tailwind and daisyUI
conventions used by the main site and the mxd sub-site, see the
[Tailwind v4 guide](tailwind-v4-guide.md) and the
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
bun run build         # build:static, build:css, build:images, build:pages, build:search
bun run build:static  # copy src/static/ verbatim (scripts/copy-static.ts)
bun run build:css     # compile src/styles/site.css and src/styles/mxd.css with Tailwind
bun run build:images  # generate responsive image variants (scripts/generate-image-variants.ts)
bun run build:pages   # uv run pages generate --all-sites
bun run build:search  # build the Netsuke search index (scripts/build-netsuke-search-index.mjs)
```

`build:static` runs first because `build:images` reads the source images it
places. `build:pages` wraps the Python generator, which can also be driven
directly:

```bash
uv run pages generate --all-sites     # main site plus every sub-site
uv run pages generate --site netsuke  # one sub-site
```

`bun run dev` (or `make dev`, which builds once first) watches `src/**/*`,
`df12_pages/**/*`, `config/**/*`, `scripts/**/*`, and `pyproject.toml` with
`chokidar`, reruns `bun run build` on any change, and serves `public/` on port
8080 with caching disabled. `DF12_PORT` overrides the port, which matters when
several worktrees are served at once.

A plain `http-server public/` — invoked directly, or via `bun run serve`, which
builds once and then serves without watching — has **no watcher**. Editing a
template, config file, or stylesheet after starting it has no effect on the
served output until `bun run build` (or `uv run pages generate`) is rerun by
hand. This is the usual reason a change appears not to have taken effect.

Run the commit gates with `make all`, which composes
`build check-fmt lint test test-js typecheck spelling` and runs them
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

## 3. Generated versus hand-crafted files

Everything under `public/` is build output and is git-ignored in its entirety.
Files placed there by hand are invisible to review and are lost the moment
anyone rebuilds from a clean tree.

Every published file has a source elsewhere in the repository:

| Published under `public/`                    | Comes from                                            |
| -------------------------------------------- | ----------------------------------------------------- |
| `**/*.html`                                  | `df12_pages` rendering `templates/` against `config/` |
| `assets/site.css`, `mxd/assets/tailwind.css` | Tailwind compiling `src/styles/`                      |
| `images/*.webp`, `images/*.avif`             | `scripts/generate-image-variants.ts`                  |
| `netsuke/assets/search/*.json`               | `scripts/build-netsuke-search-index.mjs`              |
| everything else                              | `src/static/`, copied by `scripts/copy-static.ts`     |

_Table 1: Published paths under `public/` and the source that generates them._

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
together on the Netsuke and Stilyagi sub-sites, referenced from the
[Netsuke update execution plan](execplans/netsuke-update.md).

### 4.1. Styles, lexers, and the highlight tag

Code blocks on both sub-sites are highlighted at build time by the Jinja tag
`{% highlight '<lexer>'[, '<class>'] %} ... {% endhighlight %}`, implemented in
`df12_pages/jinja_highlight.py`. The tag dedents its body, runs it through
`pygments.highlight` with the named lexer, and wraps the result in a
`<div class="hm-syntax">` (or the named class, when a second argument is given)
using `pygments.formatters.html.HtmlFormatter`. Source text containing Jinja
syntax of its own — every `Netsukefile` example with `{{ ins }}` placeholders —
must be wrapped in `{% raw %}` inside the tag.

Two Pygments styles supply the colours:

- `HimotoshiStyle` in `df12_pages/highlighting.py`, for the Netsuke sub-site.
  The module also defines `NetsukeLexer` (YAML with embedded Jinja, for
  `Netsukefile` manifests) and `NetsukeConsoleLexer` (`$`-prompted shell
  sessions with backslash continuation), both thin subclasses of stock Pygments
  lexers.
- `StilyagiStyle` in `df12_pages/stilyagi_highlighting.py`, for the Stilyagi
  sub-site.

Both styles and the two custom lexers are registered with Pygments through the
`pygments.lexers` and `pygments.styles` entry points in `pyproject.toml`, so
`get_lexer_by_name("netsuke")` and `get_style_by_name("stilyagi")` resolve
anywhere in the pipeline without an explicit import.

### 4.2. The shared helper and the division of responsibility

`scripts/pygments_css.py` provides
`token_rules(formatter, style, css_class, prefix, bold_weight)`, the single
translation from a Pygments `Style` to CSS rules, shared by
`scripts/generate_himotoshi_pygments_css.py` and
`scripts/generate_stilyagi_pygments_css.py`. Site-specific chrome —
backgrounds, padding, media queries, the surrounding wrapper markup — stays in
each generator, since that is where the two sub-sites genuinely diverge; only
the token-to-selector translation is shared.

The module exports two functions. Everything else in it is private and may be
reshaped freely.

`token_rules(formatter, style, css_class, prefix, bold_weight)` returns a
`(variables, rules)` pair: the `:root` custom-property declarations and the
selector rules, both as lists of lines in the style's own declaration order.
That order is load-bearing rather than cosmetic — a subtype's rule must follow
its ancestor's to win at equal specificity, which holds as long as the style
declares parents before children. The `formatter` must already be bound to
`style`, because it supplies both the resolved token list and the
token-to-class mapping.

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
exists specifically to close this gap for both sub-sites, and
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
- Rerun the relevant generator after any change to `HimotoshiStyle` or
  `StilyagiStyle`.
- The generators write to the tracked source under `src/static/` —
  `src/static/netsuke/assets/css/himotoshi.css` and
  `src/static/stilyagi/assets/styles/syntax.css` — never to `public/`. Writing
  to `public/` would lose the change on the next clean build.
- A test asserts the committed marked block matches what the generator would
  produce (`test_committed_stylesheet_matches_the_generator` in each test
  module below). A stale stylesheet fails the commit gates.

### 4.5. Regenerating and verifying

```bash
uv run python scripts/generate_himotoshi_pygments_css.py
uv run python scripts/generate_stilyagi_pygments_css.py
uv run pytest tests/test_netsuke_highlight.py tests/test_stilyagi_highlight.py
```

Each script is idempotent: rerunning it without changing the corresponding
style leaves the stylesheet untouched, and it reports whether it wrote a change.

### 4.6. Per-site mapping

| Site     | Style            | Lexers                                             | Wrapper class     | Variable prefix      | Bold weight | Stylesheet                                     |
| -------- | ---------------- | -------------------------------------------------- | ----------------- | -------------------- | ----------- | ---------------------------------------------- |
| Netsuke  | `HimotoshiStyle` | `netsuke`, `netsuke-console`, `toml`, `powershell` | `hm-syntax`       | `--netsuke-syntax-`  | `600`       | `src/static/netsuke/assets/css/himotoshi.css`  |
| Stilyagi | `StilyagiStyle`  | `python`                                           | `stilyagi-syntax` | `--stilyagi-syntax-` | `700`       | `src/static/stilyagi/assets/styles/syntax.css` |

_Table 2: Pygments styles, the lexers each sub-site's templates actually name
in a `{% highlight %}` tag, and the generator parameters that produce each
stylesheet._

The lexer list reflects what the templates currently use, not the full set
Pygments supports; `toml` and `powershell` are stock Pygments lexers used
unmodified. The bold weight differs because the two sub-sites' monospace faces
read differently at the same weight: Netsuke's mono face reads heavy, so its
bold stops at semibold, while Stilyagi's lighter face goes to full bold.

## 5. Template components

Repeated markup belongs in a Jinja macro, and the class list behind it belongs
in the sub-site's stylesheet. These are not alternatives: a macro whose body is
a long utility string has relocated the duplication rather than removed it, and
a component class with no macro still leaves every call site restating the
wrapper element. The "Reach for the cheapest layer that works" ladder in the
"Styling" section of [AGENTS.md](../AGENTS.md) sets out when each is warranted.

`templates/netsuke/components.jinja` holds the Netsuke sub-site's shared
macros. Import it as `ui`:

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

_Table 3: the `kicker` macro's parameters._

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

_Table 4: the kicker component class and its modifiers._

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

Bun tests under `tests/js/` cover these pure functions, and they `require` the
**built** copy from `public/`, not the source under `src/static/`:

```javascript
const { nextTabIndex } = require("../../public/netsuke/assets/js/config-keys.js");
```

This means `bun run build` (or at least `bun run build:static`) must have run
before `bun test tests/js` (`make test-js`) sees a source change; the gate runs
`build` first for exactly this reason.

Nothing here is bundled, transpiled, or module-loaded: `scripts/copy-static.ts`
copies these files verbatim. There are no ES modules, no classes, and no custom
elements anywhere on the site at the time of writing. Encapsulation is the IIFE
and nothing else, with the DOM contract expressed through `data-*` attributes
so that restyling cannot break a selector, and an early return when the root
element is absent so one `defer` script can be loaded on pages that do not use
it — `doc-search.js` is included on thirteen pages this way.

The convention's limits are worth naming, because they decide when to leave it.
A module is a file plus a `data-` prefix, so nothing enforces one instance per
root, nothing provides a lifecycle beyond first run, and nothing tells CSS that
a script has upgraded the markup — `config-keys.js` has to add an `is-enhanced`
class by hand for that. When a behaviour outgrows those limits, the next step
is a custom element in the light DOM, which supplies all three: one instance
per root, `connectedCallback`, and `:defined`. See the ladder in the "Styling"
section of [AGENTS.md](../AGENTS.md); a custom element is its last rung, and
the site does not use a front-end framework at all.

### 6.1. The config-keys component

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

The Netsuke and Weaver sub-sites still load the
[Tailwind Play CDN](https://tailwindcss.com) script
(`<script src="https://cdn.tailwindcss.com">`) rather than a compiled
stylesheet, and use its utilities in their markup alongside their own
hand-crafted stylesheets. Netsuke additionally extends the default theme
through `/netsuke/assets/js/tailwind-config.js`; Weaver takes the defaults. Of
the three hand-styled sub-sites, only Stilyagi uses neither Tailwind nor
daisyUI. This differs from the main site and the mxd sub-site, which compile
Tailwind v4 ahead of time; see the [Tailwind v4 guide](tailwind-v4-guide.md)
for that path.

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
