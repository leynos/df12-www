# Consistent Pygments highlighting for Netsuke code blocks

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: IN PROGRESS

## Purpose / big picture

The Netsuke sub-site renders code in three inconsistent ways: hand-written
`<span class="text-indigo-light">` markup with per-page colour conventions,
bare `<pre><code class="language-yaml">` blocks with no highlighting at all,
and bespoke terminal transcripts assembled from utility-classed `<div>`s. The
same YAML key is indigo on one page, amber on another, and unstyled on a
third, and every content change means hand-editing span soup.

After this change, authors write plain source text inside a template tag and
two Pygments syntaxes render it consistently everywhere:

- `netsuke` — YAML with embedded Jinja expressions (`{{ ... }}`, `{% ... %}`)
  for `Netsukefile` manifests.
- `netsuke-console` — shell sessions where lines beginning with a `$`
  prompt are commands
  (with backslash line-continuation carrying the command across lines) and
  all other lines are program output.

Both syntaxes use a single Himotoshi Pygments style so every block on the
sub-site shares one palette, and the palette lives in exactly one place.

Observable success: `templates/netsuke/pages/docs-getting-started.jinja`
contains no hand-written token spans; viewing
`http://127.0.0.1:8080/netsuke/docs/getting-started/` shows the manifest and
terminal blocks highlighted with identical colours to the manifest blocks on
`/netsuke/docs/manifest-reference/`; and the unit test
`tests/test_netsuke_highlight.py` passes, having failed before the lexers and
extension existed.

## Constraints

- The visual design language must not change: blocks keep the existing
  charcoal "faux window" chrome (`hm-faux-window`, `hm-example-code-block`,
  `hm-example-terminal`), and the palette must be drawn from the Himotoshi
  colour variables already defined in
  `public/netsuke/assets/css/himotoshi.css` (`--netsuke-indigo-light`,
  `--netsuke-matcha`, `--netsuke-amber`, `--netsuke-vermillion`,
  `--netsuke-stone-light`, `--netsuke-charcoal-light`, `--netsuke-boxwood`).
- Generated pages for the mxd, Weaver, and root sites must be byte-identical
  before and after this change; only the Netsuke sub-site and the shared
  `df12_pages` pipeline (in a backwards-compatible way) may change.
- The highlighted source text must remain copy-pasteable: rendered blocks must
  contain the literal manifest text (no soft hyphens, no line numbers in the
  copied selection).
- Manifests shown on example pages must stay verbatim copies of the shipped
  files in the netsuke repository's `examples/` directory; the migration must
  not alter their content.
- All repository quality gates must pass at every commit: `make check-fmt`,
  `make lint`, `make typecheck`, `make test`, `make spelling`, and (for this
  Markdown file) `make markdownlint` and `make nixie`.

## Tolerances (exception triggers)

- Scope: the pipeline change (lexers, style, extension, tests) should stay
  under 10 new/modified files outside `templates/netsuke/`; escalate beyond
  that. Template migration may touch every file under `templates/netsuke/`
  but must not change rendered prose.
- Dependencies: adding `jinja2-highlight` is pre-approved by the requester.
  Choosing the in-house extension instead (see Decision Log) requires no new
  dependency. Any other new dependency: stop and escalate.
- Contrast: if a palette colour fails WCAG AA contrast (4.5:1) against the
  charcoal background and no Himotoshi variable passes, escalate with a
  proposed lightened variant rather than inventing colours silently.
- Fidelity: if a migrated block's visible text differs from the original
  (beyond whitespace normalization), stop and reconcile before continuing.
- Iterations: if the lexer tests still fail after three implementation
  attempts, stop and escalate.

## Risks

- Risk: Pygments tokenizes YAML-with-Jinja differently from the hand-rolled
  colouring, so pages change appearance in detail (e.g. nested keys lose
  their amber accent because Pygments emits `Name.Tag` for every key).
  Severity: medium. Likelihood: high.
  Mitigation: treat the Pygments output as the new canon; the acceptance
  screenshots compare consistency across pages, not pixel-parity with the
  old hand-rolled markup. Note representative before/after screenshots in
  `Artefacts` for sign-off.
- Risk: `--netsuke-indigo-light` (#3A5A7C) on charcoal (#2E2A25) is
  low-contrast (~2.1:1), failing WCAG AA for key names.
  Severity: medium. Likelihood: high.
  Mitigation: the style defines dedicated `--netsuke-syntax-*` variables in
  `himotoshi.css`, initialized from the closest accessible tints of the brand
  hues; validate with the a11y contrast tooling before migration (Stage C
  gate).
- Risk: template migration moves large blocks out of `{% raw %}` regions;
  a mismatched `{% raw %}`/`{% endraw %}` pair breaks a whole page.
  Severity: medium. Likelihood: medium.
  Mitigation: migrate one template per commit, regenerate, and diff the
  rendered page text (`lynx -dump`-style extraction via BeautifulSoup)
  against the pre-migration text.
- Risk: bash embedded inside YAML command strings (e.g.
  `command: "gcc -c {{ ins }}"`) is not highlighted as bash by the stock
  `yaml+jinja` lexer; full bash-in-string delegation is complex.
  Severity: low. Likelihood: certain.
  Mitigation: explicitly out of scope for v1 (see Decision Log); the string
  colour covers the whole command. A prototyping milestone evaluates
  feasibility and records findings without blocking delivery.

## Progress

- [x] (2026-07-30 18:05Z) Stage A: plan approved by the requester,
  including the in-house extension and accessibility affordances.
- [x] (2026-07-30 18:15Z) Stage B: red tests added; all four failed for
  the expected reasons (`ClassNotFound`, `TemplateSyntaxError`).
- [x] (2026-07-30 18:35Z) Stage C: lexers, style, entry points, extension,
  environment wiring, and generated `.hm-syntax` CSS; tests green; contrast
  validated (all tokens at 5.0:1 or better; comment tint lifted to
  `#a39a8e`).
- [ ] Stage D: template migration, page by page.
- [ ] Stage E: refactor, screenshots, retrospective.

## Surprises & discoveries

- Observation: Pygments' stock `BashSessionLexer` (alias `console`) already
  implements the requested session semantics: `$`-prefixed lines lex as
  commands, a trailing backslash continues the command on the next line, and
  all other lines emit `Generic.Output`.
  Evidence: tokenizing `$ echo one \\\n    two\nresponse line\n` yields
  `Generic.Prompt`, command tokens across both lines, then
  `Generic.Output 'response line\n'`.
  Impact: `netsuke-console` is a naming/branding subclass, not new parsing
  logic.
- Observation: Pygments ships `YamlJinjaLexer` (alias `yaml+jinja`), which
  tokenizes YAML keys as `Name.Tag` and Jinja expressions with distinct
  tokens.
  Evidence: tokenizing a `Netsukefile` fragment produces `Name.Tag` for
  keys and string tokens for quoted values.
  Impact: the `netsuke` lexer is a thin subclass; effort concentrates in the
  style, CSS, and migration.

## Decision log

- Decision: the `{% highlight %}` body must wrap Jinja-bearing source in
  `{% raw %}` (documented in `df12_pages/jinja_highlight.py`).
  Rationale: Jinja lexes the tag body before any extension runs, so
  `{{ ins }}` placeholders would be interpolated away; a lexer-level tag
  like `raw` is the only way to protect them, and the sub-site templates
  already use `raw` blocks pervasively.
  Date/Author: 2026-07-30, Claude (implementation).

- Decision: implement the template tag as a small in-house Jinja extension
  (`df12_pages/jinja_highlight.py`) modelled on `jinja2-highlight`'s
  `{% highlight %}` tag, rather than depending on the `jinja2-highlight`
  package.
  Rationale: the package's last release predates 2016 and pins none of its
  behaviour; the needed functionality is ~50 lines (parse tag, dedent body,
  `pygments.highlight()` with our formatter); an in-house extension lets the
  formatter emit Himotoshi CSS classes and a window-chrome wrapper option.
  The requester allowed "jinja2-highlight or similar". Revisit if the
  in-house tag exceeds 100 lines.
  Date/Author: 2026-07-30, Claude (proposal draft).
- Decision: subclass stock lexers (`YamlJinjaLexer` → `NetsukeLexer`,
  `BashSessionLexer` → `NetsukeConsoleLexer`) instead of writing grammars
  from scratch.
  Rationale: both stock lexers already produce the required token streams
  (see Surprises); subclassing preserves upstream fixes and keeps the diff
  reviewable.
  Date/Author: 2026-07-30, Claude (proposal draft).
- Decision: highlighting bash *inside* YAML command strings is out of scope
  for v1; a bounded prototype (Stage E, optional) may explore
  `DelegatingLexer` over `command:`/`script:` scalar values.
  Rationale: the stock lexer colours command strings as strings, which is
  consistent and legible; string-internal delegation risks fragile parsing
  of block scalars for marginal gain.
  Date/Author: 2026-07-30, Claude (proposal draft).
- Decision: register the lexers and style by name through Pygments plugin
  entry points in `pyproject.toml` (`[project.entry-points."pygments.lexers"]`
  and `[project.entry-points."pygments.styles"]`).
  Rationale: makes `get_lexer_by_name('netsuke')` work everywhere (the Jinja
  tag, the Markdown docs pipeline in
  `df12_pages/generator/renderer.py`, and any future tooling) without import
  side effects.
  Date/Author: 2026-07-30, Claude (proposal draft).

## Outcomes & retrospective

To be completed at delivery.

## Context and orientation

This repository (`df12-www`) generates the df12 Productions website. The
Netsuke sub-site is generated from Jinja templates in `templates/netsuke/`
by the `pages` command (`uv run pages generate --site netsuke`), configured
in `config/pages.yaml`. Content pages are rendered by
`df12_pages/content_page.py`, which builds a Jinja `Environment` over
`templates/netsuke/` with `autoescape=True`. Generated HTML under
`public/netsuke/` is gitignored; a dev server at `http://127.0.0.1:8080/`
serves it with auto rebuild.

A separate Markdown pipeline (`df12_pages/generator/renderer.py`) already
uses Pygments with `HtmlFormatter` and a configurable style (currently
`monokai`) for the main-site docs pages; it resolves lexers with
`pygments.lexers.get_lexer_by_name`. This plan does not restyle the main
site, but name-registered lexers become available to it for free.

Today's code blocks in `templates/netsuke/` fall into three families, with
roughly one hundred blocks across fourteen templates:

1. Hand-rolled spans, e.g. `templates/netsuke/home_page.jinja` lines
   217–234: `<span class="text-indigo-light">netsuke_version</span>` etc.
   Different pages assign different colours to the same token kind.
2. Unhighlighted literals, e.g.
   `templates/netsuke/pages/examples-static-site-pipeline.jinja`:
   `<pre><code class="language-yaml">netsuke_version: "1.0.0" ...` renders
   as a single colour because nothing processes the `language-yaml` class.
3. Terminal transcripts, e.g. the "Running the Build" sections on example
   pages: sequences of utility-classed `<div>`s imitating a prompt.

"Pygments" is the Python syntax-highlighting library: a *lexer* turns source
text into a token stream, a *style* maps token types to colours, and a
*formatter* renders tokens to HTML spans with CSS classes. A *Jinja
extension* adds custom template tags to the template engine.

## Plan of work

Stage A — approval. No code changes. The requester reviews this plan;
implementation begins only on explicit approval.

Stage B — red tests. Create `tests/test_netsuke_highlight.py` with tests
that fail because the modules do not exist yet (import failure counts as the
red state; mark expected behaviours with
`@pytest.mark.xfail(strict=True, reason="netsuke lexers not implemented")`
only where imports succeed but behaviour is missing):

1. `get_lexer_by_name('netsuke')` returns a lexer whose tokens for a
   representative `Netsukefile` fragment include `Name.Tag` for keys and a
   distinct token family inside `{{ ... }}`.
2. `get_lexer_by_name('netsuke-console')` lexes `$ cargo build \\\n  --release`
   as one command spanning two lines and `Compiling netsuke` as
   `Generic.Output`.
3. `get_style_by_name('himotoshi')` exists, and its background is the
   charcoal `#2e2a25`.
4. Rendering a template through `ContentPageGenerator`'s environment with
   `{% highlight 'netsuke' %}netsuke_version: "1.0.0"{% endhighlight %}`
   produces `<div class="hm-syntax"><pre>` markup containing a
   `Name.Tag`-classed span, and the extracted text equals the input.

Stage C — pipeline implementation, in `df12_pages/`:

1. `df12_pages/highlighting.py`: define `NetsukeLexer(YamlJinjaLexer)` with
   `name='Netsuke'`, `aliases=['netsuke']`; and
   `NetsukeConsoleLexer(BashSessionLexer)` with `aliases=['netsuke-console']`.
2. In the same module, define `HimotoshiStyle(pygments.style.Style)` with
   `background_color = '#2e2a25'` and the token map below (Interfaces
   section). Register both lexers and the style via entry points in
   `pyproject.toml`; reinstall the package (`make build`) so the entry
   points load.
3. `df12_pages/jinja_highlight.py`: `HighlightExtension` implementing
   `{% highlight '<lexer>' %} ... {% endhighlight %}`: dedent the body,
   look up the lexer by name, render with
   `HtmlFormatter(cssclass='hm-syntax', wrapcode=True)`, and return the
   result marked safe. Wire the extension into the `Environment` in
   `df12_pages/content_page.py` (and `df12_pages/subsite_homepage.py`, which
   renders `home_page.jinja`).
4. CSS: add a `.hm-syntax` block to
   `public/netsuke/assets/css/himotoshi.css`, generated once from
   `HimotoshiStyle` (`python -m pygments -S` equivalent via a small
   `scripts/generate_himotoshi_pygments_css.py`, committed output, script
   kept for regeneration) and hand-scoped to the `--netsuke-syntax-*`
   variables. Validate contrast (Stage C gate) with the a11y tooling before
   proceeding.

Stage D — migration. Convert templates one per commit, starting with the
lowest-risk page and ending with the highest-traffic:
`examples-*.jinja` manifest and terminal blocks, `docs-*.jinja`,
`home_page.jinja`, `install.jinja`, `roadmap.jinja`, and the
`examples_data.jinja` card snippets' annotated-manifest siblings. For each:
replace the hand-rolled block with the tag (splicing `{% endraw %}` /
`{% raw %}` as needed), regenerate, and compare extracted block text against
the pre-migration rendering. Terminal transcripts convert to
`netsuke-console` source text (prompt lines gain a leading `$` prompt; status-only
mock transcripts stay bespoke where they are design elements rather than
code, listed explicitly during migration).

Stage E — refactor and evidence. Remove now-unused per-page `.token` style
blocks and colour conventions; capture before/after screenshots of one page
per family; optionally prototype bash-in-string delegation and record the
outcome in this plan; complete `Outcomes & retrospective`.

## Concrete steps

All commands run from the repository root.

```bash
# Stage B: red
uv run pytest tests/test_netsuke_highlight.py -q   # expect: failures/errors

# Stage C: green
make build                                          # reinstall entry points
uv run pytest tests/test_netsuke_highlight.py -q   # expect: all pass
uv run python scripts/generate_himotoshi_pygments_css.py
make check-fmt lint typecheck test spelling

# Stage D, per template:
uv run pages generate --site netsuke
# extract-and-diff of block text before/after (helper in the test module)

# Visual verification
# open http://127.0.0.1:8080/netsuke/docs/getting-started/ and compare with
# http://127.0.0.1:8080/netsuke/docs/manifest-reference/
```

## Validation and acceptance

Red: `uv run pytest tests/test_netsuke_highlight.py -q` fails before Stage C
with `ModuleNotFoundError: df12_pages.highlighting` (and strict xfails where
applicable). Green: the same command passes after Stage C with four tests.
Refactor: gates re-run clean after each Stage D commit.

Acceptance as behaviour:

1. `uv run python -c "from pygments.lexers import get_lexer_by_name;
   get_lexer_by_name('netsuke'); get_lexer_by_name('netsuke-console')"`
   exits 0.
2. On `http://127.0.0.1:8080/netsuke/docs/getting-started/` and
   `/netsuke/docs/manifest-reference/`, YAML keys, strings, and Jinja
   expressions carry identical computed colours (verified with `css-view`),
   and those colours resolve from `--netsuke-syntax-*` variables.
3. In a rendered terminal block, the `$` prefixes are visually
   distinct from output lines, and a continued command (`\` at end of line)
   is coloured as command on both lines.
4. Selecting and copying a rendered manifest block yields the original YAML
   exactly.
5. Every quality gate passes; mxd, Weaver, and root generated output is
   unchanged (`uv run pages generate --all-sites` then `git status` shows no
   tracked-file diffs outside the Netsuke work).

## Idempotence and recovery

Template migration commits are independent; a broken page is recovered with
`git checkout <file>` and regeneration. The CSS generator script is
idempotent (regenerates the same committed block). Entry-point registration
is additive; removing the `pyproject.toml` entries and reinstalling fully
reverts it.

## Artefacts and notes

To be populated during implementation: red/green test transcripts, the
generated `.hm-syntax` CSS block, and before/after screenshots of
`docs-getting-started`, one example page, and the home page code window.

## Interfaces and dependencies

No new external dependencies. Pygments (already a `df12_pages` dependency
via the docs pipeline) provides `YamlJinjaLexer`, `BashSessionLexer`,
`Style`, and `HtmlFormatter`. Jinja2 provides the extension mechanism.

In `df12_pages/highlighting.py`:

```python
class NetsukeLexer(YamlJinjaLexer):
    """YAML with embedded Jinja, as used in a Netsukefile."""
    name = "Netsuke"
    aliases = ["netsuke", "netsukefile"]
    filenames = ["Netsukefile", "*.netsuke.yml"]

class NetsukeConsoleLexer(BashSessionLexer):
    """Shell session: `$`-prefixed commands, backslash continuation, output."""
    name = "Netsuke console"
    aliases = ["netsuke-console"]

class HimotoshiStyle(Style):
    background_color = "#2e2a25"          # --netsuke-charcoal
    styles = {
        Token:                  "#e5ddd0",  # --netsuke-stone-light
        Comment:                "italic #8a8279",  # --netsuke-charcoal-light
        Name.Tag:               "#a8c3e0",  # syntax tint of indigo-light
        Literal.String:         "#8fbf9f",  # syntax tint of matcha
        Punctuation:            "#d1c7b8",  # --netsuke-stone
        Comment.Preproc:        "#e0b45c",  # Jinja markers; tint of amber
        Name.Variable:          "#e0b45c",
        Generic.Prompt:         "bold #8fbf9f",
        Generic.Output:         "#b8b0a5",
        Name.Builtin:           "#e8d5b5",  # --netsuke-boxwood
        Keyword:                "#c98a7d",  # tint of vermillion
    }
```

Exact tint values are provisional until the Stage C contrast gate; the final
values are recorded here and mirrored as `--netsuke-syntax-*` variables in
`himotoshi.css`.

In `df12_pages/jinja_highlight.py`:

```python
class HighlightExtension(Extension):
    tags = {"highlight"}
    # {% highlight 'netsuke' %}...{% endhighlight %}
    # dedents the body, resolves the lexer by name, renders with
    # HtmlFormatter(cssclass="hm-syntax", wrapcode=True), returns Markup.
```

In `pyproject.toml`:

```toml
[project.entry-points."pygments.lexers"]
netsuke = "df12_pages.highlighting:NetsukeLexer"
netsuke-console = "df12_pages.highlighting:NetsukeConsoleLexer"

[project.entry-points."pygments.styles"]
himotoshi = "df12_pages.highlighting:HimotoshiStyle"
```
