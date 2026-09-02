"""Rendering tests for the shared Netsuke page chrome.

The layout in ``doc_page.jinja``, the furniture macros in ``chrome.jinja``,
the sidebar in ``docs_nav.jinja``, and the example header in
``examples_data.jinja`` are exercised against the real templates so that
the chrome contract every Netsuke page relies on is pinned in one place.
"""

from __future__ import annotations

import typing as typ
from pathlib import Path

import pytest
from bs4 import BeautifulSoup, Tag
from jinja2 import Environment, FileSystemLoader

from df12_pages.config import ContentPageConfig, SubSiteHomepageConfig
from df12_pages.content_page import ContentPageGenerator
from df12_pages.jinja_highlight import HighlightExtension
from df12_pages.subsite_homepage import SubSiteHomePageBuilder

NETSUKE_TEMPLATES = Path("templates/netsuke").resolve()
TEMPLATE_VARS: dict[str, object] = {"netsuke_version": "0.0.0-test"}
TRAFFIC_LIGHTS = 3
ACTION_COUNT = 2

DOCS_SLUGS = [
    "",
    "getting-started",
    "manifest-reference",
    "rules-and-targets",
    "templating",
    "standard-library",
    "cli",
    "configuration",
    "security",
]


def _render_page(tmp_path: Path, template: str, output_slug: str) -> BeautifulSoup:
    """Render one Netsuke content page through the real generator."""
    config = ContentPageConfig(
        key=output_slug.replace("/", "-") or "root",
        label=output_slug,
        template=template,
        output_slug=output_slug,
    )
    generator = ContentPageGenerator(
        config,
        tmp_path / "out",
        templates_dir=NETSUKE_TEMPLATES,
        nav_links=[],
        stylesheet="assets/css/himotoshi.css",
        template_vars=TEMPLATE_VARS,
    )
    return BeautifulSoup(generator.run().read_text(encoding="utf-8"), "html.parser")


def _render_homepage(tmp_path: Path) -> BeautifulSoup:
    """Render the real Netsuke homepage through the sub-site builder."""
    config = SubSiteHomepageConfig(
        output=tmp_path / "index.html",
        title="Netsuke test homepage",
        context={},
    )
    builder = SubSiteHomePageBuilder(
        config,
        templates_dir=NETSUKE_TEMPLATES,
        nav_links=[],
        template_vars=TEMPLATE_VARS,
    )
    return BeautifulSoup(builder.run().read_text(encoding="utf-8"), "html.parser")


def _render_macro(source: str, **context: str) -> BeautifulSoup:
    """Render a template string that imports the Netsuke macro modules."""
    env = Environment(
        loader=FileSystemLoader(str(NETSUKE_TEMPLATES)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
        extensions=[HighlightExtension],
    )
    env.globals.update(TEMPLATE_VARS)
    preamble = (
        '{% import "chrome.jinja" as chrome %}'
        '{% import "docs_nav.jinja" as docsnav %}'
        '{% import "examples_data.jinja" as exdata %}'
    )
    html = env.from_string(preamble + source).render(**context)
    return BeautifulSoup(html, "html.parser")


def _classes(tag: Tag) -> list[str]:
    """Return a tag's class list, empty when it has none."""
    value = tag.get("class")
    return list(value) if isinstance(value, list) else []


def _script_sources(soup: BeautifulSoup) -> list[str]:
    return [str(tag["src"]) for tag in soup.select("script[src]")]


class TestSharedLayout:
    """The homepage and the content pages share one layout."""

    def test_homepage_renders_the_shared_navbar(self, tmp_path: Path) -> None:
        """The toggle and the menu sit inside the same mobile-nav root."""
        soup = _render_homepage(tmp_path)
        navbar = soup.select_one("nav#navbar[data-mobile-nav]")

        assert navbar is not None, "the homepage must render the layout navbar"
        assert navbar.select_one("[data-mobile-nav-toggle]") is not None, (
            "the mobile toggle belongs inside the navbar"
        )
        assert navbar.select_one("#navbar-mobile-menu[data-mobile-nav-menu]"), (
            "the mobile menu must be nested inside the navbar"
        )
        assert soup.select_one("footer#footer") is not None, (
            "the homepage must render the layout footer"
        )

    def test_homepage_overrides_the_layout_blocks(self, tmp_path: Path) -> None:
        """The homepage drops the docs scripts, adds Plotly, and unflexes the body."""
        soup = _render_homepage(tmp_path)
        sources = _script_sources(soup)

        assert not any("docs-scrollspy" in s or "copy-buttons" in s for s in sources), (
            "the homepage has no docs chrome to script"
        )
        assert any("plot.ly" in s for s in sources), "the homepage loads Plotly"
        assert any("mobile-nav.js" in s for s in sources), (
            "the shared mobile-nav script still loads"
        )
        body = soup.body
        assert body is not None
        assert "flex" not in _classes(body), (
            "the homepage body flows rather than stretching into a flex column"
        )
        assert soup.title is not None
        assert soup.title.get_text(strip=True) == "Netsuke test homepage"

    def test_content_page_keeps_the_layout_defaults(self, tmp_path: Path) -> None:
        """A docs page keeps the docs scripts and the flex body column."""
        soup = _render_page(tmp_path, "pages/docs-cli.jinja", "docs/cli")
        sources = _script_sources(soup)

        assert any("docs-scrollspy" in s for s in sources), (
            "docs pages load the scrollspy"
        )
        assert any("copy-buttons" in s for s in sources), (
            "docs pages load the copy buttons"
        )
        body = soup.body
        assert body is not None
        assert "flex" in _classes(body), "docs pages keep the flex column"
        assert not any("plot.ly" in s for s in sources), "docs pages do not load Plotly"


class TestWindows:
    """The faux window and the example terminal."""

    def test_faux_window_defaults(self) -> None:
        """The default window has the dark frame, three dots, and a label."""
        soup = _render_macro(
            "{{ chrome.faux_window_open('Netsukefile') }}<p>body</p>"
            "{{ chrome.faux_window_close() }}"
        )
        window = soup.select_one("div.hm-faux-window")

        assert window is not None, "the opener renders the window element"
        assert {"bg-charcoal", "rounded-xl", "border-charcoal-mid"} <= set(
            window["class"]
        ), "the default frame is the docs dark card"
        titlebar = window.select_one(".hm-faux-window__titlebar")
        assert titlebar is not None
        assert len(titlebar.select(".rounded-full")) == TRAFFIC_LIGHTS, (
            "three traffic lights"
        )
        label = titlebar.select_one("span")
        assert label is not None
        assert label.get_text(strip=True) == "Netsukefile"
        body = window.select_one(".hm-faux-window__body")
        assert body is not None
        assert "p-6" in body["class"], "the default body inset applies"
        assert "font-mono" in body["class"], "the default body face applies"
        content = body.select_one("p")
        assert content is not None
        assert content.get_text() == "body", (
            "the caller's content lands inside the body"
        )

    def test_faux_window_overrides(self) -> None:
        """Variant, layout, frame, and body overrides all reach the markup."""
        soup = _render_macro(
            "{{ chrome.faux_window_open('x', variant='card-bleed', "
            "outer_class='mb-8', frame='code-window', body_class='p-2') }}"
            "{{ chrome.faux_window_close() }}"
        )
        window = soup.select_one("div.hm-faux-window")

        assert window is not None
        classes = set(window["class"])
        assert "hm-faux-window--card-bleed" in classes, "variant is a modifier"
        assert "mb-8" in classes, "outer_class is appended"
        assert "code-window" in classes, "frame is rendered"
        assert "bg-charcoal" not in classes, "frame replaces the default outright"
        body = window.select_one(".hm-faux-window__body")
        assert body is not None
        assert body["class"] == ["hm-faux-window__body", "p-2"], (
            "body_class replaces the default body utilities"
        )

    def test_example_terminal(self) -> None:
        """The example terminal defaults its label and closes cleanly."""
        soup = _render_macro(
            "{{ chrome.example_terminal_open() }}<p>out</p>"
            "{{ chrome.example_terminal_close() }}"
        )
        terminal = soup.select_one("div.hm-example-terminal")

        assert terminal is not None
        label = terminal.select_one(".hm-example-terminal__titlebar > div.text-xs")
        assert label is not None
        assert label.get_text(strip=True) == "Terminal", "the default label"
        assert terminal.select_one(".hm-example-terminal__body > p") is not None, (
            "the caller's content lands inside the body"
        )


class TestPageHeader:
    """The page header in both treatments."""

    def test_docs_header(self) -> None:
        """The default header is ruled off and carries the lede."""
        soup = _render_macro(
            "{% call chrome.page_header('Reference', 'CLI & Co') %}"
            "Lede <code>x</code>{% endcall %}"
        )
        header = soup.select_one("header")

        assert header is not None
        assert "border-b" in header["class"], "the docs treatment is ruled off"
        kicker = header.select_one(".hm-kicker")
        assert kicker is not None
        assert kicker.get_text(strip=True) == "Reference"
        assert "mb-4" in kicker["class"], "the docs kicker margin"
        assert header.h1 is not None
        assert header.h1.get_text(strip=True) == "CLI & Co", (
            "the title is escaped once, not twice"
        )
        lede = header.select_one("p")
        assert lede is not None
        assert lede.select_one("code") is not None, "the lede body keeps its markup"
        assert "lg:text-5xl" in header.h1["class"]

    def test_hero_header(self) -> None:
        """The hero treatment is centred, larger, and can carry an id."""
        soup = _render_macro(
            "{% call chrome.page_header('Hub', 'Guides', hero=true, "
            "id='guides-hero', dot='bg-amber') %}Lede{% endcall %}"
        )
        header = soup.select_one("header#guides-hero")

        assert header is not None, "the id reaches the header element"
        assert "text-center" in header["class"], "the hero treatment is centred"
        assert header.h1 is not None
        assert "lg:text-6xl" in header.h1["class"], "the hero heading is larger"
        assert header.select_one(".hm-kicker__dot.bg-amber") is not None, (
            "kicker options pass through"
        )


class TestBreadcrumb:
    """The accessible breadcrumb dialect."""

    @staticmethod
    def _crumbs(source: str) -> tuple[BeautifulSoup, list[typ.Any]]:
        soup = _render_macro(source)
        return soup, soup.select("nav[aria-label='Breadcrumb'] ol > li")

    def test_two_entries(self) -> None:
        """The first crumb links, the last is the current page."""
        _soup, items = self._crumbs(
            "{{ chrome.breadcrumb([{'href': '/netsuke/docs/', 'label': 'Docs'},"
            " {'label': 'Rules & Targets'}]) }}"
        )

        assert len(items) == len(["Docs", "Rules & Targets"])
        assert items[0].a is not None
        assert items[0].a["href"] == "/netsuke/docs/"
        assert items[1].get("aria-current") == "page", (
            "the final crumb is the current page"
        )
        assert items[1].a is None, "the current page is not a link"
        assert items[1].get_text(strip=True) == "Rules & Targets", (
            "labels are escaped once"
        )

    def test_middle_entries(self) -> None:
        """A middle crumb links when it has an href and is plain text otherwise."""
        _soup, items = self._crumbs(
            "{{ chrome.breadcrumb([{'href': '/a/', 'label': 'A'},"
            " {'href': '/b/', 'label': 'B'}, {'label': 'C'}, {'label': 'D'}]) }}"
        )

        assert len(items) == len("ABCD")
        assert items[1].a is not None
        assert items[1].a["href"] == "/b/", "a middle crumb with an href links"
        assert items[2].a is None, "a middle crumb without an href is text"
        assert items[2].get_text(strip=True) == "C"
        assert [i.get("aria-current") for i in items] == [None, None, None, "page"]
        assert len(items[1].select(".iconify")) == 1, "chevrons separate crumbs"


class TestSidebarContract:
    """Every docs page renders the same sidebar with itself marked."""

    @pytest.mark.parametrize("active", DOCS_SLUGS)
    def test_sidebar_marks_exactly_the_active_page(self, active: str) -> None:
        """Order follows docs_pages and exactly one entry is active."""
        soup = _render_macro("{{ docsnav.sidebar(active) }}", active=active)
        links = soup.select("a.sidebar-link")

        hrefs = [str(link["href"]) for link in links]
        expected = [
            f"/netsuke/docs/{slug}/" if slug else "/netsuke/docs/"
            for slug in DOCS_SLUGS
        ]
        assert hrefs == expected, "the sidebar follows the shared reading order"
        active_links = [link for link in links if "active" in link["class"]]
        assert len(active_links) == 1, "exactly one entry is active"
        assert active_links[0]["href"] == expected[DOCS_SLUGS.index(active)]
        assert soup.select_one("[data-doc-search-root]") is not None, (
            "docs sidebars carry the search widget"
        )

    def test_sub_links_nest_under_the_active_page(self) -> None:
        """Anchors follow the active entry and nothing else."""
        soup = _render_macro(
            "{{ docsnav.sidebar('cli', sub_links=[{'href': '#a', 'label': 'A'},"
            " {'href': '#b', 'label': 'B'}]) }}"
        )
        links = soup.select("a.sidebar-link")

        index = next(i for i, link in enumerate(links) if "active" in link["class"])
        subs = links[index + 1 : index + 3]
        assert [s["href"] for s in subs] == ["#a", "#b"], "anchors follow the page"
        assert all("sidebar-link--sub" in s["class"] for s in subs)
        assert not any(
            "sidebar-link--sub" in link["class"] for link in links[:index]
        ), "no anchor precedes the active page"


class TestExampleHeader:
    """The example detail header renders from the catalogue."""

    def test_header_from_catalogue(self) -> None:
        """Chips, title, lede, and both actions come from the entry."""
        soup = _render_macro("{{ exdata.example_header('visual-design-assets') }}")
        header = soup.select_one("header#example-header")

        assert header is not None
        chips = [c.get_text(strip=True) for c in header.select(".hm-chip")]
        assert chips == ["Design", "Intermediate", "Reviewed syntax"]
        assert header.select_one(".hm-chip--accent") is not None, (
            "the category chip uses the entry's variant"
        )
        assert header.h1 is not None
        assert header.h1.get_text(strip=True) == "Visual Design Assets"
        buttons = header.select("a.hm-button")
        assert len(buttons) == ACTION_COUNT, "two actions"
        assert "hm-button--primary" in buttons[0]["class"], "first action is primary"
        assert "hm-button--ghost" in buttons[1]["class"], "second action is ghost"

    def test_unknown_key_renders_nothing(self) -> None:
        """An unknown key renders no header rather than a broken one."""
        soup = _render_macro("{{ exdata.example_header('no-such-example') }}")

        assert soup.select_one("header") is None
