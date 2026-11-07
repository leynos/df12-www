"""Invariants the published wireframe sub-site must hold.

The wireframe pages make promises the identity specification holds them to:
every working example is code the sample crate compiles and runs, the
release a page names is the release that crate pins, the logo is the supplied
artwork rather than a redrawing, the syntax colours are generated rather than
drawn by hand, scrolling code can be
reached from the keyboard, and legal pages carry no art. Each promise a
template edit could quietly break is asserted against the built tree here.

The ``built_site`` fixture in ``conftest.py`` runs the full ``bun run
build``. Running the samples themselves needs a Rust toolchain and the
network, so it is ``make wireframe-samples`` rather than a test here.
"""

from __future__ import annotations

import re
import textwrap
import tomllib
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from bs4 import BeautifulSoup, Tag
from PIL import Image

from df12_pages.config import load_site_config
from scripts import generate_wireframe_scope
from scripts.generate_wireframe_pygments_css import STYLESHEET, build_css

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC = REPO_ROOT / "public"
PUBLIC_SITE = PUBLIC / "wireframe"
TEMPLATES = REPO_ROOT / "templates" / "wireframe"
SAMPLES = TEMPLATES / "samples"
STYLESHEET_HREF = "/wireframe/assets/styles/wireframe.css"
LEGAL_PAGES = ("privacy-policy", "terms-of-use", "code-of-conduct")
#: The home page, fourteen content pages, and the three shared legal pages.
PUBLISHED_PAGES = 18
#: A floor on the sample panels checked, so a selector that stops matching
#: fails rather than passing vacuously.
MIN_SAMPLE_PANELS = 30

#: daisyUI component names. daisyUI emits every component into the utilities
#: layer, so any of these as a class token would restyle the element and beat
#: the sub-site's components-layer rules; the partials use `wf-` names.
DAISY_COMPONENT_TOKENS = frozenset(
    {"btn", "badge", "card", "status", "steps", "step", "timeline", "hero", "menu"}
)

#: Delimiters Jinja would read inside an included sample. The samples are
#: included with {% include %}, which parses them as templates.
JINJA_DELIMITERS = ("{{", "}}", "{%", "%}", "{#", "#}")

#: An mdBook-style anchor line, in a Rust or TOML comment.
_ANCHOR_RE = re.compile(r"^\s*(?://|#)\s*ANCHOR(?:_END)?:")

pytestmark = pytest.mark.timeout(300)


def _site():  # noqa: ANN202 - the config model is internal to df12_pages
    """Return the wireframe sub-site's configuration."""
    return load_site_config(REPO_ROOT / "config" / "pages.yaml").sites["wireframe"]


def _pages() -> list[Path]:
    """Return every published wireframe page."""
    return sorted(PUBLIC_SITE.rglob("index.html"))


def _soup(page: Path) -> BeautifulSoup:
    """Parse a published page."""
    return BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")


def _configured_routes() -> dict[str, Path]:
    """Map every route the config declares to its published page."""
    config = load_site_config(REPO_ROOT / "config" / "pages.yaml")
    site = config.sites["wireframe"]
    output = REPO_ROOT / site.output_dir
    routes: dict[str, Path] = {site.base_path: output / "index.html"}
    slugs = [page.output_slug for page in site.content_pages]
    slugs += [
        config.shared_content[ref].output_slug for ref in site.shared_content_refs
    ]
    for slug in slugs:
        routes[f"{site.base_path}{slug}/"] = output / slug / "index.html"
    return routes


def _stripped_lines(text: str) -> list[str]:
    """Return ``text``'s non-blank, non-anchor lines, dedented and stripped."""
    return [
        line.rstrip()
        for line in textwrap.dedent(text).splitlines()
        if line.strip() and not _ANCHOR_RE.match(line)
    ]


def _is_contiguous_run(excerpt: list[str], source: list[str]) -> bool:
    """Say whether ``excerpt`` appears in ``source`` as consecutive lines."""
    needle = [line.strip() for line in excerpt]
    haystack = [line.strip() for line in source]
    width = len(needle)
    return any(
        haystack[start : start + width] == needle
        for start in range(len(haystack) - width + 1)
    )


def test_every_configured_route_is_published(built_site: Path) -> None:
    """Each route in the config has a page with one h1 and the site's chrome."""
    assert built_site.is_dir()
    routes = _configured_routes()
    assert len(routes) == PUBLISHED_PAGES, sorted(routes)
    for route, page in routes.items():
        assert page.is_file(), f"{route} is configured but {page} was not built"
        soup = _soup(page)
        assert len(soup.select("h1")) == 1, f"{route}: expected one h1"
        assert soup.select_one("header.wf-mast nav[aria-label='Primary']"), route
        assert soup.select_one("main#main-content"), route


def test_every_page_links_the_compiled_stylesheet(built_site: Path) -> None:
    """Each page links the one compiled sheet, which carries the theme."""
    assert built_site.is_dir()
    css = (PUBLIC_SITE / "assets" / "styles" / "wireframe.css").read_text(
        encoding="utf-8"
    )
    assert "wireframe" in css, "the compiled sheet lacks the daisyUI theme"
    assert ".wf-syntax" in css, "the Pygments block did not compile in"
    for page in _pages():
        hrefs = [
            link.get("href") for link in _soup(page).select("link[rel=stylesheet]")
        ]
        assert hrefs == [STYLESHEET_HREF], f"{page}: {hrefs}"


def test_local_links_and_fragments_resolve(built_site: Path) -> None:
    """Every local href and src exists, and every fragment names an id."""
    assert built_site.is_dir()
    for page in _pages():
        soup = _soup(page)
        ids = [tag["id"] for tag in soup.select("[id]")]
        assert len(ids) == len(set(ids)), f"{page}: duplicate ids"
        for tag in soup.select("[href], [src]"):
            if tag.name == "use":
                continue
            url = urlsplit(str(tag.get("href") or tag.get("src")))
            if url.scheme or url.netloc:
                continue
            target = PUBLIC / unquote(url.path).lstrip("/") if url.path else page
            if target.is_dir():
                target /= "index.html"
            assert target.is_file(), f"{page}: {tag.name} points at {target}"
            if url.fragment and target.suffix == ".html":
                destination = _soup(target)
                assert destination.find(id=unquote(url.fragment)), (
                    f"{page}: no #{url.fragment} in {target}"
                )


def test_no_page_uses_a_daisyui_component_name(built_site: Path) -> None:
    """No class token on a published page is a daisyUI component name."""
    assert built_site.is_dir()
    for page in _pages():
        tokens = {
            token
            for tag in _soup(page).select("[class]")
            for token in tag.get_attribute_list("class")
        }
        clashes = tokens & DAISY_COMPONENT_TOKENS
        assert not clashes, f"{page} uses daisyUI component names {sorted(clashes)}"


def test_scrolling_regions_are_keyboard_reachable_and_labelled(
    built_site: Path,
) -> None:
    """Every code scroller and table scroller can be focused and is named."""
    assert built_site.is_dir()
    for page in _pages():
        for region in _soup(page).select(".wf-code__scroll, .wf-table-scroll"):
            assert region.get("tabindex") == "0", f"{page}: {region.get('class')}"
            assert region.get("role") == "region", f"{page}: {region.get('class')}"
            assert region.get("aria-label"), f"{page}: unlabelled scroll region"


def test_every_sample_panel_is_a_run_of_its_sample(built_site: Path) -> None:
    """A panel naming a sample shows consecutive lines of that file, verbatim.

    This is what makes "working example" true on the page: the panel is cut
    from a file ``make wireframe-samples`` compiles and runs, not retyped.
    """
    assert built_site.is_dir()
    checked = 0
    for page in _pages():
        for panel in _soup(page).select("[data-wf-sample]"):
            sample = SAMPLES / str(panel["data-wf-sample"])
            assert sample.is_file(), f"{page}: no sample {sample}"
            code = panel.select_one("pre")
            assert isinstance(code, Tag), f"{page}: sample panel without code"
            excerpt = _stripped_lines(code.get_text())
            source = _stripped_lines(sample.read_text(encoding="utf-8"))
            assert excerpt, f"{page}: empty panel for {sample.name}"
            assert _is_contiguous_run(excerpt, source), (
                f"{page}: the panel for {panel['data-wf-sample']} is not a run "
                f"of lines from that file: {excerpt[:3]}"
            )
            kind = panel.select_one(".wf-code__kind")
            assert kind is not None, f"{page}: unlabelled sample panel"
            assert kind.get_text(strip=True) == "Working example", page
            checked += 1
    assert checked >= MIN_SAMPLE_PANELS, (
        f"expected the sample panels to be checked, saw {checked}"
    )


def test_every_anchor_a_panel_names_exists() -> None:
    """Each ``code.code(file, anchor)`` call names an anchor in that file."""
    call = re.compile(r"code\.code\('([^']+)', '([^']+)'")
    calls = [
        match.groups()
        for template in TEMPLATES.rglob("*.jinja")
        for match in call.finditer(template.read_text(encoding="utf-8"))
    ]
    assert calls, "no sample panels found in the templates"
    for file, anchor in calls:
        text = (SAMPLES / file).read_text(encoding="utf-8")
        assert f"ANCHOR: {anchor}\n" in text, f"{file} has no anchor {anchor}"
        assert f"ANCHOR_END: {anchor}\n" in text, f"{file} never closes {anchor}"


def test_samples_carry_no_jinja_delimiters() -> None:
    """Every sample file survives {% include %} unchanged."""
    files = [path for path in SAMPLES.rglob("*") if path.is_file()]
    files = [path for path in files if "target" not in path.relative_to(SAMPLES).parts]
    assert files, "the sample crate is missing"
    for path in files:
        text = path.read_text(encoding="utf-8")
        found = [delimiter for delimiter in JINJA_DELIMITERS if delimiter in text]
        assert not found, f"{path.relative_to(REPO_ROOT)} contains {found}"


def test_the_sample_crate_pins_the_documented_release() -> None:
    """The crate the samples compile in depends on the release pages name."""
    manifest = tomllib.loads((SAMPLES / "Cargo.toml").read_text(encoding="utf-8"))
    template_vars = _site().template_vars
    release = template_vars["wireframe_version"]
    assert manifest["dependencies"]["wireframe"]["version"] == f"={release}"
    assert template_vars["wireframe_tag"] == f"v{release}"
    lock = tomllib.loads((SAMPLES / "Cargo.lock").read_text(encoding="utf-8"))
    locked = {package["name"]: package for package in lock["package"]}
    assert locked["wireframe"]["version"] == release
    assert ("source" in locked["wireframe"]) == template_vars["wireframe_published"], (
        "at publication, flip wireframe_published and relock against the crate; "
        "see docs/wireframe-site.md"
    )


@pytest.mark.usefixtures("built_site")
def test_the_logo_is_the_supplied_artwork() -> None:
    """Every page's brand mark is the keyed logotype, not a redrawn SVG."""
    logos = PUBLIC_SITE / "assets/logos"
    for name in ("lockup-480.webp", "lockup-800.webp", "wordmark-1400.webp"):
        with Image.open(logos / name) as image:
            assert image.mode == "RGBA", f"{name} lost its keyed alpha"
    for page in _pages():
        soup = _soup(page)
        for brand in soup.select(".wf-brand img"):
            src = str(brand.get("src", ""))
            assert src.startswith("/wireframe/assets/logos/lockup-"), page
        assert not soup.select('img[src$=".svg"][src*="/logos/"]'), (
            f"{page} still draws a logo from SVG"
        )


def test_the_scope_scene_is_generated() -> None:
    """The hero scene matches its generator, in the grammar the beam reads."""
    committed = generate_wireframe_scope.OUTPUT.read_text(encoding="utf-8")
    assert committed == generate_wireframe_scope.render(), (
        "the scope scene is stale; rerun scripts/generate_wireframe_scope.py"
    )
    roles = set(re.findall(r'data-beam="([a-z]+)"', committed))
    assert {"route", "mint", "magenta", "dim"} <= roles
    for d in re.findall(r' d="([^"]+)"', committed):
        assert re.fullmatch(r"M[-\d. ]+( L[-\d. ]+)+", d), d


def test_the_syntax_partial_is_generated() -> None:
    """The committed syntax colours match ScopeStyle."""
    assert STYLESHEET.read_text(encoding="utf-8") == build_css(), (
        f"{STYLESHEET} is stale; rerun scripts/generate_wireframe_pygments_css.py"
    )


def test_images_declare_dimensions_and_alt(built_site: Path) -> None:
    """Every image states its size, carries alt text, and is published."""
    assert built_site.is_dir()
    for page in _pages():
        for image in _soup(page).select("img"):
            assert image.get("width"), f"{page}: {image} has no width"
            assert image.get("height"), f"{page}: {image} has no height"
            assert image.has_attr("alt"), f"{page}: {image.get('src')}"
            src = str(image["src"])
            assert (PUBLIC / src.lstrip("/")).is_file(), f"{page}: {src}"


@pytest.mark.parametrize("slug", LEGAL_PAGES)
def test_legal_pages_carry_no_art(built_site: Path, slug: str) -> None:
    """A legal notice shows no plates and no diagram, only its text."""
    assert built_site.is_dir()
    soup = _soup(PUBLIC_SITE / slug / "index.html")
    main = soup.select_one("main")
    assert main is not None
    assert not main.select("img, svg, figure"), f"{slug} carries art"
    assert soup.select_one(".wf-legal"), f"{slug} lacks its body"


def test_rails_list_the_sections_of_their_page(built_site: Path) -> None:
    """An article's contents list names its sections, in order."""
    assert built_site.is_dir()
    for page in _pages():
        soup = _soup(page)
        rail = soup.select_one(".wf-aside__rail nav[aria-label='On this page']")
        if rail is None:
            continue
        listed = [a["href"] for a in rail.select("a")]
        article = soup.select_one(".wf-article")
        assert article is not None
        sections = [f"#{section['id']}" for section in article.select("section h2")]
        assert listed == sections, f"{page}: {listed} / {sections}"


def test_every_guide_is_listed_and_configured(built_site: Path) -> None:
    """The guide index lists each configured guide exactly once, in order."""
    assert built_site.is_dir()
    configured = [
        f"/wireframe/{page.output_slug}/"
        for page in _site().content_pages
        if page.output_slug.startswith("guides/")
    ]
    index = _soup(PUBLIC_SITE / "guides" / "index.html")
    listed = [a["href"] for a in index.select(".wf-route-list a")]
    assert listed == configured


def test_pages_load_their_scripts(built_site: Path) -> None:
    """Every page loads the copy script; only pages with a scope load the beam."""
    assert built_site.is_dir()
    for page in _pages():
        soup = _soup(page)
        scripts = [script.get("src") for script in soup.select("script[src]")]
        expected = ["/wireframe/assets/js/copy-code.js"]
        if soup.select("[data-wf-scope]"):
            expected.append("/wireframe/assets/js/scope.js")
        assert scripts == expected, page
    for name in ("copy-code.js", "scope.js"):
        assert (PUBLIC_SITE / "assets" / "js" / name).is_file()


_VERSION_RE = re.compile(r"(?<![\d.])0\.\d+\.\d+(?![\d.])")


def test_pages_name_only_the_documented_release(built_site: Path) -> None:
    """A version on a page is the documented release or a named exception.

    The roadmap is skipped, since it names other releases throughout. Elsewhere
    0.3.0 appears where a page speaks of migrating from it or of mxd, which
    moves on its own schedule.
    """
    assert built_site.is_dir()
    template_vars = _site().template_vars
    allowed = {
        template_vars["wireframe_version"],
        template_vars["mxd_wireframe_version"],
        "0.3.0",  # the release the migration guide starts from
        "0.1.89",  # async-trait, in the sample crate's dependencies
        "0.3.31",  # futures, likewise
        "0.7.16",  # tokio-util's floor, likewise
        "0.4.0",  # _VERSION_RE stops at the hyphen in 0.4.0-alpha1
    }
    for page in _pages():
        if page.parent.name == "roadmap":
            continue
        main = _soup(page).select_one("main")
        assert main is not None
        found = set(_VERSION_RE.findall(main.get_text(" ")))
        assert found <= allowed, f"{page}: names {sorted(found - allowed)}"
