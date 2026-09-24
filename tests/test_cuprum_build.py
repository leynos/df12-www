"""Invariants the published Cuprum sub-site must hold.

The Cuprum pages make promises the design language holds them to: code is
real and pinned to a commit, previews say they are previews, figures and
route maps point at things that exist, and fictional municipal marks stay off
legal notices. Each promise that a template edit could quietly break is
asserted against the built tree here.

The ``built_site`` fixture in ``conftest.py`` runs the full ``bun run
build``, so a missing page or stylesheet fails the suite rather than
skipping it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup, Tag

from df12_pages.config import load_site_config

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_CUPRUM = REPO_ROOT / "public" / "cuprum"
COMPILED_STYLESHEET = PUBLIC_CUPRUM / "assets" / "styles" / "cuprum.css"
LEGAL_PAGES = ("privacy-policy", "terms-of-use", "code-of-conduct")
#: The home page, eight content pages, and the three shared legal pages.
MIN_PUBLISHED_PAGES = 12

#: daisyUI component names. daisyUI emits every component into the utilities
#: layer, so any of these as a class token would restyle the element and beat
#: the sub-site's components-layer rules; the partials use `cu-` names instead.
DAISY_COMPONENT_TOKENS = frozenset(
    {"btn", "badge", "card", "status", "steps", "step", "timeline", "hero", "menu"}
)

_CLASS_ATTR_RE = re.compile(r'class="([^"]*)"')


def _site_vars() -> dict[str, object]:
    """Return the Cuprum sub-site's template variables from the config."""
    config = load_site_config(REPO_ROOT / "config" / "pages.yaml")
    return config.sites["cuprum"].template_vars


def _pages() -> list[Path]:
    """Return every published Cuprum page."""
    return sorted(PUBLIC_CUPRUM.rglob("index.html"))


def _soup(page: Path) -> BeautifulSoup:
    """Parse a published page."""
    return BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")


def _attr(tag: Tag, name: str) -> str:
    """Return a single-valued attribute as a string."""
    value = tag.get(name)
    assert isinstance(value, str), f"expected one {name!r} value on {tag.name}"
    return value


@pytest.mark.timeout(300)
def test_stylesheet_is_compiled_with_theme_and_syntax(built_site: Path) -> None:
    """The build emits the Cuprum sheet with its tokens and Pygments rules."""
    assert built_site.is_dir()
    assert COMPILED_STYLESHEET.is_file(), "is build:css:cuprum wired into build:css?"
    css = COMPILED_STYLESHEET.read_text(encoding="utf-8")
    for marker in ("--color-copper-text", ".cuprum-syntax .k", ".cu-page-head"):
        assert marker in css, f"compiled sheet is missing {marker!r}"


@pytest.mark.timeout(300)
def test_every_page_links_the_compiled_stylesheet(built_site: Path) -> None:
    """Every page loads the compiled sheet and not the Pygments source."""
    assert built_site.is_dir()
    pages = _pages()
    assert len(pages) >= MIN_PUBLISHED_PAGES, f"expected pages under {PUBLIC_CUPRUM}"
    for page in pages:
        hrefs = [link["href"] for link in _soup(page).select('link[rel="stylesheet"]')]
        assert hrefs == ["/cuprum/assets/styles/cuprum.css"], f"{page}: {hrefs}"


@pytest.mark.timeout(300)
def test_no_page_uses_a_daisyui_component_name(built_site: Path) -> None:
    """Class names stay clear of daisyUI's utilities-layer components."""
    assert built_site.is_dir()
    for page in _pages():
        tokens = {
            token
            for attr in _CLASS_ATTR_RE.findall(page.read_text(encoding="utf-8"))
            for token in attr.split()
        }
        clashes = tokens & DAISY_COMPONENT_TOKENS
        assert not clashes, f"{page} uses daisyUI component names {sorted(clashes)}"


@pytest.mark.timeout(300)
def test_code_regions_are_keyboard_reachable_and_labelled(built_site: Path) -> None:
    """Every scrolling code or output region can be focused and is named."""
    assert built_site.is_dir()
    for page in _pages():
        regions = _soup(page).select(
            ".code-scroll, .cu-output__body, .cu-slip__body, .cu-matrix-wrap"
        )
        for region in regions:
            assert region.get("tabindex") == "0", f"{page}: {region.get('class')}"
            assert region.get("role") == "region", f"{page}: {region.get('class')}"
            assert region.get("aria-label") or region.get("aria-labelledby"), (
                f"{page}: unlabelled scroll region {region.get('class')}"
            )


@pytest.mark.timeout(300)
def test_install_commands_pin_the_verified_commit(built_site: Path) -> None:
    """Install commands pin the full commit, and nothing installs Setwork.

    The documented API is on main, ahead of the PyPI release, so an unpinned
    `pip install cuprum` would install something the pages do not describe.
    Setwork has no package at all; a placeholder install would be a promise.
    """
    assert built_site.is_dir()
    commit = str(_site_vars()["cuprum_commit"])
    assert re.fullmatch(r"[0-9a-f]{40}", commit), "cuprum_commit must be a full SHA"
    commands = [
        command.get_text()
        for page in _pages()
        for command in _soup(page).select(".cu-slip__command")
    ]
    assert commands, "expected install slips on the published pages"
    for command in commands:
        assert command.endswith(f'@{commit}"'), f"unpinned install: {command}"
    for page in _pages():
        text = page.read_text(encoding="utf-8")
        assert "install setwork" not in text, f"{page} offers to install Setwork"


@pytest.mark.timeout(300)
def test_route_maps_point_at_sections_on_the_page(built_site: Path) -> None:
    """Every route-map link targets a section that exists, in order.

    The strip and the phone drop-down render from one list, so they must
    name the same sections in the same order.
    """
    assert built_site.is_dir()
    for page in _pages():
        soup = _soup(page)
        targets = [_attr(a, "href") for a in soup.select(".cu-routemap__list a")]
        menu = [_attr(a, "href") for a in soup.select(".cu-routemap__menu-list a")]
        assert menu == targets, f"{page}: the drop-down and the strip disagree"
        for number, target in enumerate(targets, start=1):
            section = soup.select_one(target)
            assert section is not None, f"{page}: {target} has no section"
            kicker = section.select_one(".cu-kicker")
            assert kicker is not None
            assert kicker.get_text().startswith(f"{number:02d} "), (
                f"{page}: {target} is numbered {kicker.get_text()!r}"
            )


@pytest.mark.timeout(300)
def test_only_published_examples_have_pages(built_site: Path) -> None:
    """Pending job sheets are listed, never linked, and have no page."""
    assert built_site.is_dir()
    index = _soup(PUBLIC_CUPRUM / "examples" / "index.html")
    for card in index.select(".cu-card--pending"):
        assert card.select_one("a") is None, "a pending example must not link"
    hrefs = {_attr(a, "href") for a in index.select(".cu-card__title a")}
    linked = {href for href in hrefs if href.startswith("/cuprum/examples/")}
    assert linked, "expected published examples on the index"
    for href in linked:
        assert (REPO_ROOT / "public" / href.strip("/") / "index.html").is_file(), href


@pytest.mark.timeout(300)
def test_seal_stays_off_legal_pages(built_site: Path) -> None:
    """The fictional crest appears in the chrome, but never on a legal notice."""
    assert built_site.is_dir()
    for page in _pages():
        seals = _soup(page).select("svg.cu-seal")
        is_legal = page.parent.name in LEGAL_PAGES
        if is_legal:
            assert not seals, f"{page} is a legal notice and carries a seal"
        else:
            assert seals, f"{page} should carry the colophon seal"
        for seal in seals:
            assert seal.get("aria-hidden") == "true", f"{page}: seal is decorative"


@pytest.mark.timeout(300)
def test_images_declare_dimensions_and_alt(built_site: Path) -> None:
    """Every image reserves its box and states an alternative, even if empty."""
    assert built_site.is_dir()
    for page in _pages():
        for image in _soup(page).select("img"):
            assert image.has_attr("alt"), f"{page}: {image.get('src')} has no alt"
            assert image.get("width"), f"{page}: {image.get('src')} has no width"
            assert image.get("height"), f"{page}: {image.get('src')} has no height"
            src = _attr(image, "src")
            source = REPO_ROOT / "public" / src.lstrip("/")
            assert source.is_file(), f"{page}: {src} is not published"


@pytest.mark.timeout(300)
def test_previews_say_so_in_their_heading(built_site: Path) -> None:
    """Preview pages carry their status in words at the top, not only colour."""
    assert built_site.is_dir()
    expectations = {
        "internals/rust-extension": "Technical preview",
        "setwork": "Proposed",
    }
    for slug, word in expectations.items():
        head = _soup(PUBLIC_CUPRUM / slug / "index.html").select_one(".cu-page-head")
        assert head is not None
        statuses = [s.get_text(strip=True) for s in head.select(".cu-status")]
        assert word in statuses, f"/cuprum/{slug}/ header statuses: {statuses}"


@pytest.mark.timeout(300)
def test_engraving_masks_are_published(built_site: Path) -> None:
    """Every mask the compiled sheet names is a published file.

    The skyline and the town hall are CSS masks, not images, so a missing
    file leaves an invisible box rather than a broken-image icon.
    """
    assert built_site.is_dir()
    css = COMPILED_STYLESHEET.read_text(encoding="utf-8")
    masks = set(re.findall(r'mask-image:url\("?(/cuprum/[^")]+)"?\)', css))
    assert any("town-hall" in mask for mask in masks), sorted(masks)
    for mask in masks:
        assert (REPO_ROOT / "public" / mask.lstrip("/")).is_file(), mask
