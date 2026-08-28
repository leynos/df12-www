"""Invariants the Weaver sub-site must hold after its daisyUI migration.

The Weaver sub-site is moving off the Tailwind Play CDN onto the repository's
compiled Tailwind v4 and daisyUI v5 pipeline. See
``docs/execplans/weaver-daisy-migration.md``. Three properties define "done",
and each is asserted here so a later change cannot quietly undo one:

1. The stylesheet is compiled by the build rather than assembled in the
   browser.
2. No published Weaver page reaches a third-party host at runtime.
3. Colour is declared once, in the theme, rather than restated as literals
   throughout the markup and the partials.

Each was written failing, and each carried a strict ``xfail`` marker naming
the milestone that would turn it green — a marker left in place after the
behaviour arrived would itself fail the suite, so none could be forgotten. All
three now pass on their own.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_WEAVER = REPO_ROOT / "public" / "weaver"
WEAVER_TEMPLATES = REPO_ROOT / "templates" / "weaver"
WEAVER_STYLES = REPO_ROOT / "src" / "styles"
WEAVER_STATIC = REPO_ROOT / "src" / "static" / "weaver"
COMPILED_STYLESHEET = PUBLIC_WEAVER / "assets" / "styles" / "weaver.css"


# An attribute that makes the browser fetch from another origin. `href` counts
# only on a `<link>`; on an `<a>` it is a link to somewhere else, which is the
# point of a link.
#
# `srcset` needs its own alternative. Its value is a comma-separated candidate
# list, so a remote host can sit anywhere in it — `/local.png 1x,
# //cdn/remote.png 2x` is a fetch from another origin that an anchored pattern
# reads as local, because it only ever looked at the first candidate.
SUBRESOURCE = re.compile(
    r"""(?:src|data|poster)\s*=\s*["']\s*(?:https?:)?//"""
    r"""|srcset\s*=\s*["'](?:[^"']*,)?\s*(?:https?:)?//"""
    r"""|<link\b[^>]*?\bhref\s*=\s*["']\s*(?:https?:)?//"""
    r"""|url\(\s*["']?\s*(?:https?:)?//"""
    r"""|@import\s+(?:url\(\s*)?["']\s*(?:https?:)?//""",
    re.IGNORECASE,
)


# A rule the typography plugin emits and nothing else does.
#
# Searching for `prose` alone passes vacuously: daisyUI ships its own
# compatibility rules — `.prose .btn` and `.prose :where(code)` — so both the
# word and the `.prose :where(...)` shape appear in the compiled sheet whether
# or not the plugin is registered. That is how `prose prose-indigo` sat
# unstyled in three templates without anything noticing.
#
# The `not-prose` escape hatch belongs to the plugin alone; it appears nowhere
# else in the dependency tree. Anchoring it to the paragraph rule keeps the
# assertion a concrete selector rather than a substring search.
PROSE_RULE = re.compile(
    r"""\.prose\s+:where\(p\):not\(:where\(\[class~=["']?not-prose"""
)


# Three- to eight-digit hex colours, and any rgb()/rgba() call. Deliberately
# broad: the point is that a colour literal has no business outside the theme,
# whatever notation it wears.
HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b")


RGB_COLOUR = re.compile(r"\brgba?\(")


# In a template, only `class` and `style` attributes carry styling. The
# design-system page prints the palette's hex codes as its own content, which
# is the page's whole job and not a colour anyone is specifying.
STYLING_ATTRIBUTE = re.compile(r"""(?:class|style)\s*=\s*(?:"[^"]*"|'[^']*')""")


def _weaver_sources() -> list[Path]:
    """List the files that must not contain a colour literal.

    Returns
    -------
    list of Path
        Every Weaver template and every Weaver stylesheet partial, plus the
        sub-site's Tailwind entrypoint's sibling directory. The entrypoint
        itself, ``src/styles/weaver.css``, is excluded: it is the one file
        where colour is declared.
    """
    sources = sorted(WEAVER_TEMPLATES.rglob("*.jinja"))
    weaver_partials = WEAVER_STYLES / "weaver"
    if weaver_partials.is_dir():
        sources.extend(sorted(weaver_partials.rglob("*.css")))
    return sources


@pytest.mark.timeout(300)
def test_weaver_stylesheet_is_compiled(built_site: Path) -> None:
    """The build should emit a Weaver stylesheet carrying the daisyUI theme."""
    assert COMPILED_STYLESHEET.is_file(), (
        f"expected a compiled stylesheet at {COMPILED_STYLESHEET}; "
        "is build:css:weaver wired into build:css?"
    )
    compiled = COMPILED_STYLESHEET.read_text(encoding="utf-8")
    assert "--color-primary" in compiled, (
        "expected the compiled stylesheet to define the daisyUI theme slots; "
        "found no --color-primary"
    )
    # Three templates carry `prose prose-indigo`, which styled nothing at all
    # between the Play CDN's removal and this assertion. See PROSE_RULE for why
    # the selector has to be this specific to catch that.
    assert PROSE_RULE.search(compiled), (
        "expected the compiled stylesheet to carry @tailwindcss/typography's "
        "prose rules; is the @plugin registration still in src/styles/weaver.css?"
    )


@pytest.mark.timeout(300)
def test_weaver_pages_reach_no_third_party_hosts(built_site: Path) -> None:
    """No published Weaver page should load anything from another origin.

    This looks at the attributes that make a browser fetch something rather
    than at a list of hosts someone thought of. The list version passed for
    several commits while four illustrations on the design-system page were
    still being served from Google Cloud Storage. Editorial ``<a href>`` links
    to other sites are left alone: pointing somewhere else is what a link is
    for.
    """
    offenders: dict[str, list[str]] = {}
    for page in sorted(built_site.rglob("*.html")):
        markup = page.read_text(encoding="utf-8")
        remote = sorted({m.group(0)[:80] for m in SUBRESOURCE.finditer(markup)})
        if remote:
            offenders[str(page.relative_to(built_site))] = remote

    assert not offenders, (
        "expected every Weaver page to be self-contained, but these fetch "
        f"subresources from elsewhere: {offenders}"
    )


def test_weaver_sources_declare_no_colour_literals() -> None:
    """Colour should live in the theme, not be restated across the sources."""
    offenders: dict[str, list[str]] = {}
    for source in _weaver_sources():
        text = source.read_text(encoding="utf-8")
        if source.suffix == ".jinja":
            text = "\n".join(STYLING_ATTRIBUTE.findall(text))
        literals = HEX_COLOUR.findall(text) + RGB_COLOUR.findall(text)
        if literals:
            relative = str(source.relative_to(REPO_ROOT))
            # Report a sample rather than every hit; a file with two hundred
            # of them is no more informative than one showing five.
            offenders[relative] = sorted(set(literals))[:5]

    assert not offenders, (
        "expected colour to be declared only in src/styles/weaver.css, but "
        f"found literals in: {offenders}"
    )


@pytest.mark.parametrize(
    ("markup", "is_styling"),
    [
        ('<div class="bg-[#fdf8f0]">', True),
        ("<div class='bg-[#fdf8f0]'>", True),
        ('<div style="color: #fff">', True),
        ("<div style='color: #fff'>", True),
        ('<div class = "bg-white">', True),
        # The design-system page prints hex codes as its own content, which is
        # the page's job and not a colour anyone is specifying.
        ("<p>The ground is #f3efd9</p>", False),
    ],
)
def test_styling_attribute_matches_either_quote_style(
    markup: str,
    *,
    is_styling: bool,
) -> None:
    """The colour scan must not miss a single-quoted attribute.

    While the pattern required double quotes, a colour literal written with
    single quotes was invisible to it, and the test that relies on it would
    have passed regardless of what the attribute contained.
    """
    assert bool(STYLING_ATTRIBUTE.search(markup)) is is_styling


@pytest.mark.parametrize(
    ("markup", "is_remote"),
    [
        ('<img src="https://storage.googleapis.com/x.png">', True),
        ('<img src="//cdn.example.com/x.png">', True),
        ('<script src="https://cdn.tailwindcss.com"></script>', True),
        ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2">', True),
        ('<img src="/weaver/assets/x.png">', False),
        ('<link rel="stylesheet" href="/weaver/assets/styles/weaver.css">', False),
        # A link to somewhere else is what a link is for.
        ('<a href="https://github.com/leynos/weaver">source</a>', False),
        ('<a class="btn" href="https://example.com">read</a>', False),
        # CSS and embedded media reach other origins by their own routes.
        ("<style>a{background:url(https://cdn.example.com/x.png)}</style>", True),
        ('<style>@import url("//cdn.example.com/a.css");</style>', True),
        ('<object data="https://example.com/x.pdf"></object>', True),
        ('<video poster="//cdn.example.com/p.jpg"></video>', True),
        # Every url() the built site actually contains is a local path, and
        # none of them may be read as a remote fetch.
        (
            "<style>a{background:url('/weaver/assets/textures/cubes.png')}</style>",
            False,
        ),
        ("<style>a{background:url(/weaver/assets/fonts/x.woff2)}</style>", False),
        ("<style>a{mask:url(#a)}</style>", False),
        # A srcset names several candidates. Only the first sits against the
        # opening quote, so the remote one hides behind a local one.
        ('<img srcset="//cdn.example.com/x.png 2x">', True),
        ('<img srcset="/weaver/a.png 1x, //cdn.example.com/a@2x.png 2x">', True),
        (
            '<img srcset="/weaver/a.png 1x, https://cdn.example.com/a@2x.png 2x">',
            True,
        ),
        ('<img srcset="/weaver/a.png 1x, /weaver/a@2x.png 2x">', False),
    ],
)
def test_subresource_pattern_distinguishes_fetches_from_links(
    markup: str,
    *,
    is_remote: bool,
) -> None:
    """The self-contained check must not pass vacuously, or ban hyperlinks."""
    verdict = "remote" if is_remote else "local"
    assert bool(SUBRESOURCE.search(markup)) is is_remote, (
        f"expected SUBRESOURCE to read this as {verdict}: {markup}"
    )


def test_no_font_awesome_markup_remains() -> None:
    """Every Font Awesome glyph should have become an inline SVG.

    The scripts and stylesheets are scanned as well as the templates. While
    this covered templates alone it passed with `mobile-nav.js` still writing
    ``<i class="fa-solid fa-bars">`` into the drawer's toggle at runtime — a
    Font Awesome glyph with no Font Awesome behind it, which rendered as an
    empty box on every page below 1024px. Scanning the built HTML would not
    have caught it either: that markup does not exist until the script runs.
    """
    sources = [
        path
        for path in WEAVER_TEMPLATES.rglob("*.jinja")
        # The generated macro is the one file allowed to name the old classes:
        # its documentation shows the markup it replaces.
        if path.name != "_icons.jinja"
    ]
    sources += sorted(WEAVER_STATIC.rglob("*.js"))
    sources += sorted(WEAVER_STATIC.rglob("*.css"))

    offenders = {
        str(path.relative_to(REPO_ROOT))
        for path in sources
        if re.search(
            r"""class\s*=\s*["'][^"']*\bfa(?:-(?:solid|regular|brands|fw)|[srb]?)\b""",
            path.read_text(encoding="utf-8"),
        )
    }
    assert not offenders, f"Font Awesome classes remain in: {offenders}"
