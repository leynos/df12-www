"""Invariants the published rstest-bdd sub-site must hold.

The rstest-bdd pages make promises the design language holds them to: every
code sample is the code the sample crate compiles and runs, the release they
name is the release that crate pins, scrolling code can be reached from the
keyboard, the guide rails point at sections that exist, and the felt cast
stays off legal notices. Each promise a template edit could quietly break is
asserted against the built tree here.

The ``built_site`` fixture in ``conftest.py`` runs the full ``bun run
build``, so a missing page or stylesheet fails the suite rather than
skipping it. Running the samples themselves needs a Rust toolchain and the
network, so it is ``make rstest-bdd-samples`` rather than a test here.
"""

from __future__ import annotations

import re
import textwrap
import tomllib
from pathlib import Path

import pytest
from bs4 import BeautifulSoup, Tag

from df12_pages.config import load_site_config

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_SITE = REPO_ROOT / "public" / "rstest-bdd"
TEMPLATES = REPO_ROOT / "templates" / "rstest-bdd"
SAMPLES = TEMPLATES / "samples"
COMPILED_STYLESHEET = PUBLIC_SITE / "assets" / "styles" / "rstest-bdd.css"
STYLESHEET_HREF = "/rstest-bdd/assets/styles/rstest-bdd.css"
LEGAL_PAGES = ("privacy-policy", "terms-of-use", "code-of-conduct")
#: The home page, twelve content pages, and the three shared legal pages.
PUBLISHED_PAGES = 16
#: Pages with a section rail: the seven guides, getting started, harnesses.
PAGES_WITH_RAILS = 9
#: A floor on the sample panels checked, so a selector that stops matching
#: fails rather than passing vacuously.
MIN_SAMPLE_PANELS = 40

#: daisyUI component names. daisyUI emits every component into the utilities
#: layer, so any of these as a class token would restyle the element and beat
#: the sub-site's components-layer rules; the partials use `rb-` names instead.
DAISY_COMPONENT_TOKENS = frozenset(
    {"btn", "badge", "card", "status", "steps", "step", "timeline", "hero", "menu"}
)

#: Delimiters Jinja would read inside an included sample. The samples are
#: included verbatim with {% include %}, which parses them as templates, so
#: any of these would be executed or swallowed rather than published.
JINJA_DELIMITERS = ("{{", "}}", "{%", "%}", "{#", "#}")


def _site():  # noqa: ANN202 - the config model is internal to df12_pages
    """Return the rstest-bdd sub-site's configuration."""
    return load_site_config(REPO_ROOT / "config" / "pages.yaml").sites["rstest-bdd"]


def _pages() -> list[Path]:
    """Return every published rstest-bdd page."""
    return sorted(PUBLIC_SITE.rglob("index.html"))


def _soup(page: Path) -> BeautifulSoup:
    """Parse a published page."""
    return BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")


def _configured_routes() -> dict[str, Path]:
    """Map every route the config declares to its published page."""
    config = load_site_config(REPO_ROOT / "config" / "pages.yaml")
    site = config.sites["rstest-bdd"]
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
    """Return ``text``'s non-blank lines, dedented and right-stripped."""
    return [
        line.rstrip() for line in textwrap.dedent(text).splitlines() if line.strip()
    ]


def _is_contiguous_run(excerpt: list[str], source: list[str]) -> bool:
    """Say whether ``excerpt`` appears in ``source`` as consecutive lines.

    Lines are compared with leading whitespace removed as well, so an excerpt
    may be dedented relative to the file it was cut from.
    """
    needle = [line.strip() for line in excerpt]
    haystack = [line.strip() for line in source]
    width = len(needle)
    return any(
        haystack[start : start + width] == needle
        for start in range(len(haystack) - width + 1)
    )


@pytest.mark.timeout(300)
def test_every_configured_route_is_published(built_site: Path) -> None:
    """Each route in the config has a page with one h1 and the site's chrome.

    The routes come from ``config/pages.yaml`` rather than from the built
    tree, so a page the build silently drops fails here by name.
    """
    assert built_site.is_dir()
    routes = _configured_routes()
    assert len(routes) == PUBLISHED_PAGES, sorted(routes)
    for route, page in routes.items():
        assert page.is_file(), f"{route} is configured but {page} was not built"
        soup = _soup(page)
        assert len(soup.select("h1")) == 1, f"{route}: expected one h1"
        assert soup.select_one("header.rb-mast nav[aria-label='Primary']"), route
        assert soup.select_one("main#main-content"), route


@pytest.mark.timeout(300)
def test_every_page_links_the_compiled_stylesheet(built_site: Path) -> None:
    """Each page links the one compiled sheet, which carries the theme."""
    assert built_site.is_dir()
    css = COMPILED_STYLESHEET.read_text(encoding="utf-8")
    assert "rstest-bdd" in css, "the compiled sheet lacks the daisyUI theme"
    assert ".lantern-syntax" in css, "the Pygments block did not compile in"
    for page in _pages():
        hrefs = [
            link.get("href") for link in _soup(page).select("link[rel=stylesheet]")
        ]
        assert hrefs == [STYLESHEET_HREF], f"{page}: {hrefs}"


@pytest.mark.timeout(300)
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


@pytest.mark.timeout(300)
def test_scrolling_regions_are_keyboard_reachable_and_labelled(
    built_site: Path,
) -> None:
    """Every code scroller and the storybook strip can be focused and is named."""
    assert built_site.is_dir()
    for page in _pages():
        for region in _soup(page).select(".rb-code-scroll, .rb-story__track"):
            assert region.get("tabindex") == "0", f"{page}: {region.get('class')}"
            assert region.get("role") == "region", f"{page}: {region.get('class')}"
            assert region.get("aria-label"), f"{page}: unlabelled scroll region"


@pytest.mark.timeout(300)
def test_every_sample_panel_is_a_run_of_its_sample(built_site: Path) -> None:
    """A panel naming a sample shows consecutive lines of that file, verbatim.

    This is what makes "compiled and run against rstest-bdd" true on the
    page: the panel's code is cut from a file ``make rstest-bdd-samples``
    compiles and runs, not retyped beside it. It also holds the rendered
    dependency versions to the crate's Cargo.toml.
    """
    assert built_site.is_dir()
    checked = 0
    for page in _pages():
        for panel in _soup(page).select("[data-rb-sample]"):
            sample = SAMPLES / str(panel["data-rb-sample"])
            assert sample.is_file(), f"{page}: no sample {sample}"
            code = panel.select_one("pre")
            assert isinstance(code, Tag), f"{page}: sample panel without code"
            excerpt = _stripped_lines(code.get_text())
            source = _stripped_lines(sample.read_text(encoding="utf-8"))
            assert excerpt, f"{page}: empty panel for {sample.name}"
            assert _is_contiguous_run(excerpt, source), (
                f"{page}: the panel for {panel['data-rb-sample']} is not a run "
                f"of lines from that file: {excerpt[:3]}"
            )
            checked += 1
    assert checked >= MIN_SAMPLE_PANELS, (
        f"expected the sample panels to be checked, saw {checked}"
    )


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
    """The crate the samples compile in depends on the versions pages name."""
    manifest = tomllib.loads((SAMPLES / "Cargo.toml").read_text(encoding="utf-8"))
    deps = manifest["dev-dependencies"]
    template_vars = _site().template_vars
    release = template_vars["rstest_bdd_version"]
    for crate in (
        "rstest-bdd",
        "rstest-bdd-macros",
        "rstest-bdd-harness",
        "rstest-bdd-harness-tokio",
    ):
        assert deps[crate] == release, f"{crate} is {deps[crate]}, pages say {release}"
    assert deps["rstest"] == template_vars["rstest_version"]
    assert manifest["package"]["rust-version"] == template_vars["rust_floor"]
    assert template_vars["rstest_bdd_tag"] == f"v{release}"


@pytest.mark.timeout(300)
def test_images_declare_dimensions_and_alt(built_site: Path) -> None:
    """Every image states its size and carries an alt attribute."""
    assert built_site.is_dir()
    for page in _pages():
        for image in _soup(page).select("img"):
            assert image.get("width"), f"{page}: {image} has no width"
            assert image.get("height"), f"{page}: {image} has no height"
            assert image.has_attr("alt"), f"{page}: {image.get('src')}"
            src = str(image["src"])
            assert (REPO_ROOT / "public" / src.lstrip("/")).is_file(), (
                f"{page}: {src} is not published"
            )


@pytest.mark.timeout(300)
def test_figures_are_captioned(built_site: Path) -> None:
    """Every illustration names who is in it, in a caption."""
    assert built_site.is_dir()
    for page in _pages():
        for figure in _soup(page).select("figure.rb-figure"):
            caption = figure.select_one("figcaption")
            assert caption is not None, f"{page}: uncaptioned figure"
            assert caption.get_text(strip=True), f"{page}: empty caption"


@pytest.mark.timeout(300)
@pytest.mark.parametrize("slug", LEGAL_PAGES)
def test_legal_pages_carry_no_illustration(built_site: Path, slug: str) -> None:
    """A legal notice shows no characters and no line crediting them."""
    assert built_site.is_dir()
    page = PUBLIC_SITE / slug / "index.html"
    soup = _soup(page)
    assert not soup.select("img"), f"{slug} carries an image"
    assert "plushie" not in soup.get_text(), f"{slug} credits the illustrations"
    assert soup.select_one(".rb-legal"), f"{slug} lacks its body"


@pytest.mark.timeout(300)
def test_rails_list_the_sections_of_their_page(built_site: Path) -> None:
    """A page's rail and drop-down both list its sections, in order.

    Both render from one `sections` list in the template, as the sections'
    ids should; this holds the three to each other.
    """
    assert built_site.is_dir()
    rails = 0
    for page in _pages():
        soup = _soup(page)
        toc = soup.select_one("nav.rb-toc")
        if toc is None:
            continue
        rails += 1
        rail = [a["href"] for a in toc.select(".rb-toc__rail a")]
        menu = [a["href"] for a in toc.select(".rb-toc__menu a")]
        body = soup.select_one(".rb-guide__body")
        assert body is not None, f"{page}: rail without a body"
        sections = [f"#{section['id']}" for section in body.select(":scope > section")]
        assert rail == menu == sections, f"{page}: {rail} / {menu} / {sections}"
    assert rails == PAGES_WITH_RAILS, (
        f"expected the guides, getting started, and harnesses; saw {rails}"
    )


@pytest.mark.timeout(300)
def test_every_guide_is_listed_and_configured(built_site: Path) -> None:
    """The pattern book lists each configured guide exactly once, in order."""
    assert built_site.is_dir()
    configured = [
        f"/rstest-bdd/{page.output_slug}/"
        for page in _site().content_pages
        if page.output_slug.startswith("guides/")
    ]
    index = _soup(PUBLIC_SITE / "guides" / "index.html")
    listed = [
        card["href"]
        for card in index.select("a.rb-card")
        if str(card["href"]).startswith("/rstest-bdd/guides/")
    ]
    assert listed == configured


@pytest.mark.timeout(300)
def test_the_storybook_tabs_target_its_chapters(built_site: Path) -> None:
    """Eight chapters, eight tabs, and each tab is a link to its chapter."""
    assert built_site.is_dir()
    soup = _soup(PUBLIC_SITE / "index.html")
    chapters = [chapter["id"] for chapter in soup.select("[data-rb-chapter]")]
    tabs = [tab["href"] for tab in soup.select("[data-rb-chapter-tab]")]
    assert chapters == [f"chapter-{n:02d}" for n in range(1, 9)]
    assert tabs == [f"#{chapter}" for chapter in chapters]
    paging = soup.select_one("[data-rb-story-paging]")
    assert paging is not None, "the storybook lacks its paging controls"
    assert paging.has_attr("hidden"), "paging must stay hidden until the script runs"


@pytest.mark.timeout(300)
def test_pages_load_their_scripts(built_site: Path) -> None:
    """Every page loads the copy script; the home page also the storybook."""
    assert built_site.is_dir()
    for page in _pages():
        scripts = [script.get("src") for script in _soup(page).select("script[src]")]
        assert "/rstest-bdd/assets/js/copy-code.js" in scripts, page
        for src in scripts:
            assert (REPO_ROOT / "public" / str(src).lstrip("/")).is_file(), src
    home = [s.get("src") for s in _soup(PUBLIC_SITE / "index.html").select("script")]
    assert "/rstest-bdd/assets/js/storybook.js" in home


_VERSION_RE = re.compile(r"\b0\.\d+\.\d+\b")


@pytest.mark.timeout(300)
def test_pages_name_only_the_documented_release(built_site: Path) -> None:
    """A version number on a page is the documented release or a known one.

    Old releases appear by design on the roadmap, in the migration guide,
    and in the tooling guide's warning that the language server on crates.io
    is behind; the rest of the site names only the release its samples were
    run against.
    """
    assert built_site.is_dir()
    template_vars = _site().template_vars
    allowed = {template_vars["rstest_bdd_version"], template_vars["rstest_version"]}
    for page in _pages():
        if page.parent.name in {"roadmap", "migrate-to-0-6", "tooling"}:
            continue
        main = _soup(page).select_one("main")
        assert main is not None
        found = set(_VERSION_RE.findall(main.get_text(" ")))
        assert found <= allowed, f"{page}: names {sorted(found - allowed)}"
