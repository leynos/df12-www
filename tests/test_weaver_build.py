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

import importlib.util
import re
import shutil
import subprocess
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
SUBRESOURCE = re.compile(
    r"""(?:src|srcset)\s*=\s*["']\s*(?:https?:)?//"""
    r"""|<link\b[^>]*?\bhref\s*=\s*["']\s*(?:https?:)?//""",
    re.IGNORECASE,
)

# Three- to eight-digit hex colours, and any rgb()/rgba() call. Deliberately
# broad: the point is that a colour literal has no business outside the theme,
# whatever notation it wears.
HEX_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}\b")
RGB_COLOUR = re.compile(r"\brgba?\(")

# In a template, only `class` and `style` attributes carry styling. The
# design-system page prints the palette's hex codes as its own content, which
# is the page's whole job and not a colour anyone is specifying.
STYLING_ATTRIBUTE = re.compile(r'(?:class|style)="[^"]*"')


@pytest.fixture(scope="session")
def built_site() -> Path:
    """Build the published tree and return the Weaver sub-site's root.

    Returns
    -------
    Path
        ``public/weaver`` after a successful build.
    """
    bun_exe = shutil.which("bun")
    if not bun_exe:  # pragma: no cover - environment guard
        message = "Unable to locate 'bun' on PATH"
        raise FileNotFoundError(message)
    subprocess.run([bun_exe, "run", "build"], cwd=REPO_ROOT, check=True)  # noqa: S603 - fixed argv, no user input
    if not PUBLIC_WEAVER.is_dir():  # pragma: no cover - defensive
        message = f"expected the Weaver sub-site at {PUBLIC_WEAVER}"
        raise FileNotFoundError(message)
    return PUBLIC_WEAVER


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
    assert built_site.is_dir()


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


def test_generated_icon_macro_matches_its_source() -> None:
    """The committed icon macro should be what the generator produces.

    ``templates/weaver/_icons.jinja`` is generated from
    ``config/weaver-icons.yaml`` and the ``@iconify-json/carbon`` package. A
    hand-edit there, or a mapping change without a regeneration, would survive
    unnoticed otherwise.
    """
    spec = importlib.util.spec_from_file_location(
        "generate_weaver_icons", REPO_ROOT / "scripts" / "generate_weaver_icons.py"
    )
    assert spec is not None
    assert spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)

    if not generator.CARBON.is_file():  # pragma: no cover - environment guard
        pytest.skip("@iconify-json/carbon is not installed; run 'bun install'")

    expected = generator.build_macro()
    actual = generator.OUTPUT.read_text(encoding="utf-8")
    assert actual == expected, (
        "templates/weaver/_icons.jinja is out of date; run "
        "'uv run python scripts/generate_weaver_icons.py'"
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
            r"\bfa-(solid|regular|brands|fw)\b", path.read_text(encoding="utf-8")
        )
    }
    assert not offenders, f"Font Awesome classes remain in: {offenders}"


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
    ],
)
def test_subresource_pattern_distinguishes_fetches_from_links(
    markup: str,
    *,
    is_remote: bool,
) -> None:
    """The self-contained check must not pass vacuously, or ban hyperlinks."""
    assert bool(SUBRESOURCE.search(markup)) is is_remote
