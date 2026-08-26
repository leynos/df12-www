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
import typing as typ
from pathlib import Path

if typ.TYPE_CHECKING:
    from types import ModuleType

import jinja2
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

# `{{ icon('name') }}` as the templates write it, in either quote form.
ICON_CALL = re.compile(r"""icon\(\s*(?:'([^']+)'|"([^"]+)")""")


# `built_site` is a session fixture in tests/conftest.py, shared with
# tests/test_weaver_browser.py so the build runs once for both.


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


@pytest.fixture(scope="module")
def generator() -> ModuleType:
    """Load the icon generator, which is a script rather than an importable module."""
    spec = importlib.util.spec_from_file_location(
        "generate_weaver_icons", REPO_ROOT / "scripts" / "generate_weaver_icons.py"
    )
    assert spec is not None, "scripts/generate_weaver_icons.py could not be located"
    assert spec.loader is not None, (
        "spec for generate_weaver_icons has no loader; it cannot be executed"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_icon_macro_matches_its_source(generator: ModuleType) -> None:
    """The committed icon macro should be what the generator produces.

    ``templates/weaver/_icons.jinja`` is generated from
    ``config/weaver-icons.yaml`` and the ``@iconify-json/carbon`` package. A
    hand-edit there, or a mapping change without a regeneration, would survive
    unnoticed otherwise.
    """
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
            r"""class\s*=\s*["'][^"']*\bfa(?:-(?:solid|regular|brands|fw)|[srb]?)\b""",
            path.read_text(encoding="utf-8"),
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


def test_the_icon_macro_renders_from_data_without_reading_a_file(
    generator: ModuleType,
) -> None:
    """The rendering is pure, so a handful of literal icons is enough to check it."""
    macro = generator.render_macro(
        {
            "terminal": {"body": "<path d='M0 0'/>"},
            "star": {"body": "<path d='M1 1'/>"},
        },
        {"asterisk": {"parent": "star"}},
        {
            "fa-terminal": {"carbon": "carbon:terminal"},
            "fa-star": {"carbon": "carbon:asterisk"},
        },
    )

    assert "'terminal': '<path d=\\'M0 0\\'/>'" in macro, (
        f"the mapped icon should carry its escaped body; got {macro!r}"
    )
    assert "'star': '<path d=\\'M1 1\\'/>'" in macro, (
        f"an alias should resolve to its parent's body; got {macro!r}"
    )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(("{ not json", None, "malformed"), id="carbon-malformed"),
        pytest.param(('{"aliases": {}}', None, "'icons'"), id="carbon-no-icons"),
        pytest.param((None, "icons: [1, 2]", "'icons'"), id="mapping-not-a-mapping"),
        pytest.param(
            (None, "not: a mapping of icons", "'icons'"), id="mapping-no-icons"
        ),
        # The nested records are somebody else's format too, and a scalar where
        # a record was expected raises TypeError rather than KeyError — which
        # `build_macro`'s handler does not catch.
        pytest.param(
            ('{"icons": {"terminal": 5}}', None, "'body'"), id="carbon-icon-scalar"
        ),
        pytest.param(
            ('{"icons": {"terminal": {"width": 32}}}', None, "'body'"),
            id="carbon-icon-no-body",
        ),
        pytest.param(
            ('{"icons": {"terminal": {"body": 7}}}', None, "'body'"),
            id="carbon-icon-body-not-a-string",
        ),
        pytest.param(
            ('{"icons": {}, "aliases": {"star": "asterisk"}}', None, "'parent'"),
            id="carbon-alias-scalar",
        ),
        pytest.param(
            ('{"icons": {}, "aliases": {"star": {"rotate": 1}}}', None, "'parent'"),
            id="carbon-alias-no-parent",
        ),
        pytest.param(
            ('{"icons": {}, "aliases": [1, 2]}', None, "'aliases'"),
            id="carbon-aliases-not-a-mapping",
        ),
        pytest.param(
            (None, "icons:\n  fa-ghost: 5\n", "'carbon'"), id="mapping-record-scalar"
        ),
        pytest.param(
            (None, "icons:\n  fa-ghost:\n    note: no carbon here\n", "'carbon'"),
            id="mapping-record-no-carbon",
        ),
        pytest.param(
            (None, "icons:\n  fa-ghost:\n    carbon: [a, b]\n", "'carbon'"),
            id="mapping-carbon-not-a-string",
        ),
    ],
)
def test_an_unusable_generator_input_names_the_file(
    generator: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case: tuple[str | None, str | None, str],
) -> None:
    """A traceback out of json or ruamel names neither the file nor the fix."""
    carbon, mapping, expected = case
    carbon_path = tmp_path / "icons.json"
    carbon_path.write_text(carbon or '{"icons": {}}', encoding="utf-8")
    mapping_path = tmp_path / "weaver-icons.yaml"
    mapping_path.write_text(mapping or "icons: {}", encoding="utf-8")
    monkeypatch.setattr(generator, "CARBON", carbon_path)
    monkeypatch.setattr(generator, "MAPPING", mapping_path)

    with pytest.raises(SystemExit) as caught:
        generator.build_macro()

    message = str(caught.value.code)
    at_fault = carbon_path if carbon is not None else mapping_path
    assert str(at_fault) in message, (
        f"the message should name {at_fault}; got {message!r}"
    )
    assert expected in message, f"expected {expected!r} in {message!r}"


def test_an_absent_carbon_package_names_the_command_that_installs_it(
    generator: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The one failure with a known fix should say what the fix is."""
    monkeypatch.setattr(generator, "CARBON", tmp_path / "absent.json")

    with pytest.raises(SystemExit) as caught:
        generator.build_macro()

    assert "bun install" in str(caught.value.code), (
        f"the message should name the fix; got {caught.value.code!r}"
    )


def test_an_unmapped_carbon_icon_names_the_mapping(
    generator: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A mapping naming an icon the package lacks is an editing mistake, not a crash."""
    carbon_path = tmp_path / "icons.json"
    carbon_path.write_text('{"icons": {"terminal": {"body": ""}}}', encoding="utf-8")
    mapping_path = tmp_path / "weaver-icons.yaml"
    mapping_path.write_text(
        "icons:\n  fa-ghost:\n    carbon: carbon:no-such-icon\n", encoding="utf-8"
    )
    monkeypatch.setattr(generator, "CARBON", carbon_path)
    monkeypatch.setattr(generator, "MAPPING", mapping_path)

    with pytest.raises(SystemExit) as caught:
        generator.build_macro()

    message = str(caught.value.code)
    assert str(mapping_path) in message, (
        f"the message should name the mapping; got {message!r}"
    )
    assert "no-such-icon" in message, f"expected the icon named in {message!r}"


def _minimal_inputs(
    generator: ModuleType, monkeypatch: pytest.MonkeyPatch, root: Path
) -> None:
    """Point the generator at a pair of valid inputs that render an empty macro."""
    carbon_path = root / "icons.json"
    carbon_path.write_text('{"icons": {}}', encoding="utf-8")
    mapping_path = root / "weaver-icons.yaml"
    mapping_path.write_text("icons: {}", encoding="utf-8")
    monkeypatch.setattr(generator, "CARBON", carbon_path)
    monkeypatch.setattr(generator, "MAPPING", mapping_path)


class _UnwritablePath(Path):
    """A path that reads like any other and refuses every write.

    ``main`` reads ``OUTPUT`` before it writes it, so the write handler is only
    reachable through something that lets the read succeed. Pointing ``OUTPUT``
    at a directory does not do that: ``Path.exists()`` is true for one and
    ``read_text()`` raises ``IsADirectoryError``, so the *read* handler fires
    and the write handler is never entered at all.
    """

    def write_text(self, *_args: object, **_kwargs: object) -> int:
        """Fail the way a read-only tree or a full disk would."""
        message = f"Permission denied: {self}"
        raise PermissionError(message)


def test_an_unwritable_output_reports_the_path_rather_than_an_oserror(
    generator: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`main` is the CLI boundary, so its filesystem failures exit with a message."""
    _minimal_inputs(generator, monkeypatch, tmp_path)

    output = _UnwritablePath(tmp_path / "_icons.jinja")
    # Existing and readable, and holding something other than what the
    # generator will produce, so `main` gets past its unchanged short-circuit
    # and reaches the write.
    Path(output).write_text("stale", encoding="utf-8")
    monkeypatch.setattr(generator, "OUTPUT", output)

    with pytest.raises(SystemExit) as caught:
        generator.main()

    message = str(caught.value.code)
    assert str(output) in message, (
        f"the message should name the output; got {message!r}"
    )
    assert "could not be written" in message, (
        f"the write handler should be the one that fired; got {message!r}"
    )


def test_an_unreadable_output_is_reported_separately(
    generator: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The read and the write are distinct failures and say so distinctly."""
    _minimal_inputs(generator, monkeypatch, tmp_path)

    # A directory exists and cannot be read as text, which is the read handler's
    # case and not the write handler's.
    output = tmp_path / "_icons.jinja"
    output.mkdir()
    monkeypatch.setattr(generator, "OUTPUT", output)

    with pytest.raises(SystemExit) as caught:
        generator.main()

    message = str(caught.value.code)
    assert str(output) in message, (
        f"the message should name the output; got {message!r}"
    )
    assert "could not be read" in message, (
        f"the read handler should be the one that fired; got {message!r}"
    )


# A Tailwind font-size utility, as a whole class token. Anchored at both ends
# so `text-base-content` is not read as `text-base`, which is the mistake that
# makes a naive search of this markup report duplicates that are not there.
FONT_SIZE = re.compile(r"^text-(?:[3-9]xs|2xs|xs|sm|base|lg|xl|[2-9]xl)$")

# Both quote forms. `templates/weaver/_icons.jinja` is single-quoted, so a
# double-quote-only pattern skips it entirely — and it is generated, which is
# exactly the kind of file nobody would notice going unchecked.
CLASS_ATTRIBUTE = re.compile(r"""class\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.DOTALL)


def test_no_element_declares_two_font_sizes_at_once() -> None:
    """Two font-size utilities on one element make the winner a source-order accident.

    The Sempai page carried `text-xs ... text-3xs` on one contents link for
    several commits: the later class won, so that one link rendered smaller
    than its eight siblings and nothing said why. Commit `16dd6ae1` resolved it
    by dropping `text-3xs`, since `text-xs` is what the other eight carry.

    Only unprefixed utilities are counted. A responsive variant beside a base
    size — `text-sm md:text-base` — is the intended way to change size at a
    breakpoint, not a duplicate.
    """
    offenders: dict[str, list[str]] = {}
    for source in sorted(WEAVER_TEMPLATES.rglob("*.jinja")):
        # Matched against the whole file rather than line by line: a `class`
        # attribute long enough to be wrapped would otherwise be seen as two
        # fragments, neither of which is an attribute, and a duplicate split
        # across the wrap would go unreported. The line number comes from the
        # match offset, and the offset keys the report, so two attributes on
        # one line are both kept.
        text = source.read_text(encoding="utf-8")
        for attribute in CLASS_ATTRIBUTE.finditer(text):
            value = attribute.group(1) or attribute.group(2) or ""
            sizes = [token for token in value.split() if FONT_SIZE.match(token)]
            if len(sizes) > 1:
                number = text.count("\n", 0, attribute.start()) + 1
                where = f"{source.relative_to(REPO_ROOT)}:{number}+{attribute.start()}"
                offenders[where] = sizes

    assert not offenders, (
        "these elements declare more than one font size, so which one applies "
        f"depends on the order the utilities happen to be written in: {offenders}"
    )


@pytest.mark.parametrize(
    ("markup", "expected"),
    [
        pytest.param(
            '<div class="text-xs text-3xs">',
            ["text-xs", "text-3xs"],
            id="double-quoted-duplicate",
        ),
        pytest.param(
            "<div class='text-xs text-3xs'>",
            ["text-xs", "text-3xs"],
            id="single-quoted-duplicate",
        ),
        pytest.param(
            '<div class="text-sm md:text-base lg:text-lg">',
            ["text-sm"],
            id="double-quoted-responsive",
        ),
        pytest.param(
            "<div class='text-sm md:text-base lg:text-lg'>",
            ["text-sm"],
            id="single-quoted-responsive",
        ),
        pytest.param(
            '<div class="text-xs text-base-content/82">',
            ["text-xs"],
            id="a-colour-token-is-not-a-size",
        ),
        pytest.param('<div class="font-mono">', [], id="no-size-at-all"),
    ],
)
def test_the_scan_reads_class_attributes_in_either_quote_form(
    markup: str, expected: list[str]
) -> None:
    """A double-quote-only pattern skipped `_icons.jinja`, which is single-quoted.

    The value is captured by one group or the other depending on which quote
    the attribute used, so both have to be consulted; taking only the first
    would read a single-quoted attribute as empty and report no sizes at all.
    """
    found = [
        token
        for attribute in CLASS_ATTRIBUTE.finditer(markup)
        for token in (attribute.group(1) or attribute.group(2) or "").split()
        if FONT_SIZE.match(token)
    ]
    assert found == expected, f"expected {expected} in {markup!r}, found {found}"


@pytest.mark.parametrize(
    ("classes", "expected"),
    [
        # The reason the pattern is anchored: a colour token that starts with
        # a size's name is not a size.
        ("text-xs text-base-content/82", 1),
        ("block pl-4 text-xs text-base-content/82 hover:text-accent-ink", 1),
        ("text-xs text-3xs", 2),
        # A breakpoint variant is how a size is meant to change, not a clash.
        ("text-sm md:text-base lg:text-lg", 1),
        ("font-mono tracking-stamp", 0),
    ],
)
def test_the_font_size_pattern_counts_whole_tokens(classes: str, expected: int) -> None:
    """The check is only as good as its ability to tell a size from a colour."""
    sizes = [token for token in classes.split() if FONT_SIZE.match(token)]
    assert len(sizes) == expected, (
        f"expected {expected} font-size utilities in {classes!r}, found {sizes}"
    )


@pytest.fixture(scope="module")
def icon_macro() -> typ.Callable[..., str]:
    """Load `_icons.jinja` through Jinja and return its `icon` macro.

    The generated file is compared against the generator elsewhere, which
    proves the two agree and nothing more: both could agree on markup Jinja
    refuses to parse, or on a macro that renders an empty string. Rendering it
    is what shows it works.
    """
    environment = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(WEAVER_TEMPLATES)),
        autoescape=True,
    )
    module = environment.get_template("_icons.jinja").module
    # The macro is an attribute of the rendered module, which is dynamic, so
    # the type checker cannot see it; that it exists at all is the first thing
    # these tests assert.
    macro = getattr(module, "icon", None)
    assert macro is not None, (
        "templates/weaver/_icons.jinja defines no `icon` macro; every call "
        "site in every Weaver template would render nothing"
    )
    return typ.cast("typ.Callable[..., str]", macro)


def test_the_generated_macro_renders_an_svg(icon_macro: typ.Callable[..., str]) -> None:
    """A macro that parses but renders nothing would pass every other check."""
    rendered = str(icon_macro("terminal"))

    assert rendered.startswith("<svg "), f"expected an <svg> element; got {rendered!r}"
    assert 'viewBox="0 0 32 32"' in rendered, f"no viewBox in {rendered!r}"
    assert 'aria-hidden="true"' in rendered, (
        f"the artwork is decorative and must be hidden from assistive "
        f"technology; got {rendered!r}"
    )
    assert "<path" in rendered or "<circle" in rendered, (
        f"the icon rendered no artwork at all: {rendered!r}"
    )


def test_the_generated_macro_carries_extra_classes(
    icon_macro: typ.Callable[..., str],
) -> None:
    """`extra_class` is how a call site sizes or colours one instance."""
    rendered = str(icon_macro("terminal", extra_class="text-accent-ink w-6"))

    assert "text-accent-ink w-6" in rendered, (
        f"the per-instance classes were dropped: {rendered!r}"
    )
    assert "inline-block" in rendered, (
        f"the macro's own classes should survive alongside them: {rendered!r}"
    )


def test_an_unmapped_icon_name_is_loud_rather_than_blank(
    icon_macro: typ.Callable[..., str],
) -> None:
    """A missing icon that rendered nothing would leave a hole nobody noticed."""
    rendered = str(icon_macro("definitely-not-an-icon"))

    assert "UNKNOWN ICON" in rendered, (
        f"an unmapped name should say so rather than render empty; got {rendered!r}"
    )
    assert "definitely-not-an-icon" in rendered, (
        f"the message should name the icon asked for; got {rendered!r}"
    )


def test_every_icon_the_templates_ask_for_renders(
    icon_macro: typ.Callable[..., str],
) -> None:
    """A template naming an icon the macro lacks ships `UNKNOWN ICON` to a page.

    The browser suite catches this on the four pages it loads at a time; this
    catches it across every template, without a browser.
    """
    asked = {
        match.group(1) or match.group(2)
        for source in WEAVER_TEMPLATES.rglob("*.jinja")
        if source.name != "_icons.jinja"
        for match in ICON_CALL.finditer(source.read_text(encoding="utf-8"))
    }
    assert asked, "no icon calls were found at all; has the call syntax changed?"

    missing = sorted(name for name in asked if "UNKNOWN ICON" in str(icon_macro(name)))
    assert not missing, (
        f"these icons are used in the templates but absent from the generated "
        f"macro, so each renders the literal text 'UNKNOWN ICON': {missing}"
    )
