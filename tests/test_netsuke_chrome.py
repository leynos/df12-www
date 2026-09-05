"""Rendering tests for the shared Netsuke page chrome.

The layout in ``doc_page.jinja``, the furniture macros in ``chrome.jinja``,
the sidebar in ``docs_nav.jinja``, and the example header in
``examples_data.jinja`` are exercised against the real templates so that
the chrome contract every Netsuke page relies on is pinned in one place.
"""

from __future__ import annotations

import re
import typing as typ
from pathlib import Path

import pytest
from bs4 import BeautifulSoup, Tag
from hypothesis import given, settings
from hypothesis import strategies as st
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


def _render_macro(source: str, **context: object) -> BeautifulSoup:
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
        assert body is not None, "the homepage has a body"
        assert "flex" not in _classes(body), (
            "the homepage body flows rather than stretching into a flex column"
        )
        assert soup.title is not None, "the homepage has a title"
        assert soup.title.get_text(strip=True) == "Netsuke test homepage", (
            "the configured title reaches the page_title block"
        )

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
        assert body is not None, "the docs page has a body"
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
        assert {"bg-base-content", "rounded-xl", "border-charcoal-mid"} <= set(
            window["class"]
        ), "the default frame is the docs dark card"
        titlebar = window.select_one(".hm-faux-window__titlebar")
        assert titlebar is not None, "the window has a titlebar"
        assert len(titlebar.select(".rounded-full")) == TRAFFIC_LIGHTS, (
            "three traffic lights"
        )
        label = titlebar.select_one("span")
        assert label is not None, "the titlebar carries a label"
        assert label.get_text(strip=True) == "Netsukefile", (
            "the label is the caller's text"
        )
        body = window.select_one(".hm-faux-window__body")
        assert body is not None, "the window has a body"
        assert "p-6" in body["class"], "the default body inset applies"
        assert "font-mono" in body["class"], "the default body face applies"
        content = body.select_one("p")
        assert content is not None, "the body holds the caller's content"
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

        assert window is not None, "the opener renders the window element"
        classes = set(window["class"])
        assert "hm-faux-window--card-bleed" in classes, "variant is a modifier"
        assert "mb-8" in classes, "outer_class is appended"
        assert "code-window" in classes, "frame is rendered"
        assert "bg-base-content" not in classes, "frame replaces the default outright"
        body = window.select_one(".hm-faux-window__body")
        assert body is not None, "the window has a body"
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

        assert terminal is not None, "the opener renders the terminal element"
        label = terminal.select_one(".hm-example-terminal__titlebar > div.text-xs")
        assert label is not None, "the titlebar carries a label"
        assert label.get_text(strip=True) == "Terminal", "the default label"
        assert terminal.select_one(".hm-example-terminal__body > p") is not None, (
            "the caller's content lands inside the body"
        )

    @pytest.mark.parametrize(
        ("opener", "closer", "selector"),
        [
            ("faux_window_open('x')", "faux_window_close()", "div.hm-faux-window"),
            (
                "example_terminal_open()",
                "example_terminal_close()",
                "div.hm-example-terminal",
            ),
        ],
    )
    def test_closer_closes_the_window(
        self, opener: str, closer: str, selector: str
    ) -> None:
        """Content after the closer sits outside the window, not inside it."""
        soup = _render_macro(
            "{{ chrome." + opener + " }}<p id='inside'>in</p>"
            "{{ chrome." + closer + " }}<p id='after'>after</p>"
        )
        window = soup.select_one(selector)

        assert window is not None, "the opener renders the window"
        assert window.select_one("#inside") is not None, (
            "content before the closer is inside the window"
        )
        assert window.select_one("#after") is None, (
            "content after the closer is outside the window"
        )
        assert soup.select_one("#after") is not None, (
            "the trailing content still renders"
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

        assert header is not None, "the macro renders a header element"
        assert "border-b" in header["class"], "the docs treatment is ruled off"
        kicker = header.select_one(".hm-kicker")
        assert kicker is not None, "the header carries a kicker pill"
        assert kicker.get_text(strip=True) == "Reference", "the kicker label"
        assert "mb-4" in kicker["class"], "the docs kicker margin"
        assert header.h1 is not None, "the header carries an h1"
        assert header.h1.get_text(strip=True) == "CLI & Co", (
            "the title is escaped once, not twice"
        )
        lede = header.select_one("p")
        assert lede is not None, "the header carries a lede paragraph"
        assert lede.select_one("code") is not None, "the lede body keeps its markup"
        assert "lg:text-5xl" in header.h1["class"], "the docs heading size"

    def test_hero_header(self) -> None:
        """The hero treatment is centred, larger, and can carry an id."""
        soup = _render_macro(
            "{% call chrome.page_header('Hub', 'Guides', hero=true, "
            "id='guides-hero', dot='bg-warning') %}Lede{% endcall %}"
        )
        header = soup.select_one("header#guides-hero")

        assert header is not None, "the id reaches the header element"
        assert "text-center" in header["class"], "the hero treatment is centred"
        assert header.h1 is not None, "the header carries an h1"
        assert "lg:text-6xl" in header.h1["class"], "the hero heading is larger"
        assert header.select_one(".hm-kicker__dot.bg-warning") is not None, (
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
        assert items[0].a is not None, "the first crumb is a link"
        assert items[0].a["href"] == "/netsuke/docs/", "the first crumb's href"
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

        assert len(items) == len("ABCD"), "one item per crumb"
        assert items[1].a is not None, "a middle crumb with an href is a link"
        assert items[1].a["href"] == "/b/", "a middle crumb with an href links"
        assert items[2].a is None, "a middle crumb without an href is text"
        assert items[2].get_text(strip=True) == "C", "the plain crumb keeps its label"
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
        assert active_links[0]["href"] == expected[DOCS_SLUGS.index(active)], (
            "the active entry is the requested page"
        )
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
        assert all("sidebar-link--sub" in s["class"] for s in subs), (
            "anchors carry the sub modifier"
        )
        assert not any(
            "sidebar-link--sub" in link["class"] for link in links[:index]
        ), "no anchor precedes the active page"


EXAMPLE_HEADERS: dict[str, tuple[str, str, str, str, list[tuple[str, str, str]]]] = {
    "hello-world": (
        "Basics",
        "warning",
        "Beginner",
        "Hello World",
        [
            ("/netsuke/examples/", "carbon:arrow-left", "Back to Examples"),
            ("/netsuke/docs/getting-started/", "carbon:book", "Getting Started"),
        ],
    ),
    "static-site-pipeline": (
        "Web",
        "brand",
        "Intermediate",
        "Static Site Pipeline",
        [
            ("/netsuke/examples/", "carbon:arrow-left", "Back to Examples"),
            ("/netsuke/docs/rules-and-targets/", "carbon:book", "Rules & Targets"),
        ],
    ),
    "batch-photo-processing": (
        "Media",
        "success",
        "Intermediate",
        "Batch Photo Processing",
        [
            ("/netsuke/examples/", "carbon:arrow-left", "Back to Examples"),
            ("/netsuke/docs/templating/", "carbon:template", "Templating Guide"),
        ],
    ),
    "visual-design-assets": (
        "Design",
        "accent",
        "Intermediate",
        "Visual Design Assets",
        [
            ("/netsuke/examples/", "carbon:arrow-left", "Back to Examples"),
            ("/netsuke/docs/templating/", "carbon:template", "Templating Guide"),
        ],
    ),
    "basic-c-application": (
        "C / C++",
        "brand",
        "Beginner",
        "Basic C Application",
        [
            (
                "https://github.com/leynos/netsuke/archive/refs/heads/main.zip",
                "carbon:download",
                "Download Repository Source",
            ),
            (
                "https://github.com/leynos/netsuke/blob/main/examples/basic_c.yml",
                "carbon:logo-github",
                "View on GitHub",
            ),
        ],
    ),
    "multi-format-documentation": (
        "Docs",
        "muted",
        "Intermediate",
        "Multi-Format Documentation",
        [
            ("/netsuke/examples/", "carbon:arrow-left", "Back to Examples"),
            ("/netsuke/docs/rules-and-targets/", "carbon:book", "Rules & Targets"),
        ],
    ),
}


EXAMPLE_LEDES: dict[str, str] = {
    "hello-world": (
        "The smallest useful Netsuke manifest in this repository. One target "
        "transforms `input.txt`, another writes a greeting from a variable, and "
        "`defaults` tell the CLI what to build when you just run `netsuke`."
    ),
    "static-site-pipeline": (
        "Compile each Markdown page into HTML, then rebuild a shared index from "
        "the generated output. This example is small on purpose: it shows "
        "`foreach`, `order_only_deps`, and reusable rules without hiding the "
        "graph."
    ),
    "batch-photo-processing": (
        "Convert a directory of RAW files into JPEG output and then regenerate a "
        "gallery page from the resulting images. This example shows how Netsuke "
        "fans one rule over many files and still finishes with a single top-level "
        "artefact."
    ),
    "visual-design-assets": (
        "Rasterise a list of SVG designs into PNG output with Inkscape. The "
        "manifest keeps the Inkscape command configurable through a plain "
        "`inkscape` variable, alongside `foreach` and a dedicated clean action, "
        "without turning a small asset pipeline into a custom script."
    ),
    "basic-c-application": (
        "A foundational example demonstrating how to compile two C sources and "
        "link them into one executable. The point is the manifest language, not a "
        "rule loader."
    ),
    "multi-format-documentation": (
        "Convert chapter Markdown into TeX, assemble a PDF with `latexmk`, and "
        "keep the build directory itself under explicit control. This example is "
        "about document pipelines, not marketing-site fluff."
    ),
}


class TestExampleHeader:
    """The example detail header renders from the catalogue."""

    @pytest.mark.parametrize("key", sorted(EXAMPLE_HEADERS))
    def test_header_from_catalogue(self, key: str) -> None:
        """Chips, title, lede, and both actions come from the entry."""
        category, variant, level, title, actions = EXAMPLE_HEADERS[key]
        soup = _render_macro("{{ exdata.example_header(key) }}", key=key)
        header = soup.select_one("header#example-header")

        assert header is not None, "the macro renders the example header"
        chips = header.select(".hm-chip")
        assert [c.get_text(strip=True) for c in chips] == [
            category,
            level,
            "Reviewed syntax",
        ], "category, level, and review chips in that order"
        assert f"hm-chip--{variant}" in chips[0]["class"], (
            "the category chip uses the entry's variant"
        )
        assert "hm-chip--muted" in chips[1]["class"], "the level chip is muted"
        assert "hm-chip--success" in chips[2]["class"], "the review chip is success"
        assert header.h1 is not None, "the header carries an h1"
        assert header.h1.get_text(strip=True) == title, (
            "the title comes from the catalogue entry"
        )
        lede = header.select_one("p")
        assert lede is not None, "the header carries a lede"
        assert lede.get_text(strip=True) == EXAMPLE_LEDES[key], (
            "the lede is the catalogue entry's text, rendered exactly"
        )
        buttons = header.select("a.hm-button")
        rendered = []
        for button in buttons:
            icon = button.select_one(".iconify")
            assert icon is not None, "every action carries an icon"
            rendered.append(
                (
                    str(button["href"]),
                    str(icon["data-icon"]),
                    button.get_text(strip=True),
                )
            )
        assert rendered == actions, (
            "both actions carry the entry's href, icon, and label"
        )
        assert "hm-button--primary" in buttons[0]["class"], "first action is primary"
        assert "hm-button--ghost" in buttons[1]["class"], "second action is ghost"

    def test_unknown_key_renders_nothing(self) -> None:
        """An unknown key renders no header rather than a broken one."""
        soup = _render_macro("{{ exdata.example_header('no-such-example') }}")

        assert soup.select_one("header") is None, "an unknown key renders no header"


_LABELS = (
    st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
        min_size=1,
        max_size=24,
    )
    .map(str.strip)
    .filter(bool)
)
_CRUMB = st.fixed_dictionaries(
    {"label": _LABELS},
    optional={"href": st.from_regex(r"\A/[a-z0-9/-]{0,20}\Z")},
)


class TestListContracts:
    """Property checks for the macros that take caller-supplied lists."""

    @given(trail=st.lists(_CRUMB, min_size=1, max_size=6))
    @settings(max_examples=60, deadline=None)
    def test_breadcrumb_renders_every_crumb_in_order(
        self, trail: list[dict[str, str]]
    ) -> None:
        """One item per crumb, order kept, exactly the last marked current."""
        soup = _render_macro("{{ chrome.breadcrumb(trail) }}", trail=trail)
        items = soup.select("nav[aria-label='Breadcrumb'] ol > li")

        assert [i.get_text(strip=True) for i in items] == [c["label"] for c in trail], (
            "labels render in trail order, escaped once"
        )
        assert [i.get("aria-current") for i in items] == [None] * (len(trail) - 1) + [
            "page"
        ], "exactly the final crumb is the current page"
        assert len(soup.select("nav[aria-label='Breadcrumb'] .iconify")) == (
            len(trail) - 1
        ), "one chevron precedes every crumb after the first"
        for index, (item, crumb) in enumerate(zip(items, trail, strict=True)):
            link = item.a
            if index == len(trail) - 1:
                assert link is None, "the current page is never a link"
            elif index == 0 or "href" in crumb:
                assert link is not None, "a leading or href-bearing crumb links"
                assert link["href"] == crumb.get("href", ""), "the link target"
            else:
                assert link is None, "a middle crumb without an href is text"

    @given(
        sections=st.lists(
            st.fixed_dictionaries(
                {
                    "title": _LABELS,
                    "links": st.lists(
                        st.fixed_dictionaries(
                            {
                                "href": st.from_regex(r"\A#[a-z][a-z0-9-]{0,12}\Z"),
                                "label": _LABELS,
                            },
                            optional={
                                "sub": st.booleans(),
                                "active": st.just(value=True),
                            },
                        ),
                        min_size=1,
                        max_size=5,
                    ),
                },
                optional={"sub": st.just(value=True)},
            ),
            min_size=1,
            max_size=4,
        )
    )
    @settings(max_examples=40, deadline=None)
    def test_sidebar_sections_render_in_order(
        self, sections: list[dict[str, object]]
    ) -> None:
        """Bespoke sections keep their order, links, and per-link states."""
        soup = _render_macro(
            "{{ docsnav.sidebar(sections=sections, search=false) }}",
            sections=sections,
        )
        groups = soup.select("#sidebar nav > div")

        assert [g.h3.get_text(strip=True) for g in groups if g.h3] == [
            s["title"] for s in sections
        ], "one heading per section, in order"
        for group, section in zip(groups, sections, strict=True):
            links = group.select("a.sidebar-link")
            expected = section["links"]
            assert isinstance(expected, list)
            assert [(str(a["href"]), a.get_text(strip=True)) for a in links] == [
                (link["href"], link["label"]) for link in expected
            ], "links render in order with their targets"
            for anchor, link in zip(links, expected, strict=True):
                assert isinstance(link, dict)
                wants_sub = bool(link.get("sub", section.get("sub", False)))
                assert ("sidebar-link--sub" in anchor["class"]) == wants_sub, (
                    "a link's own sub flag wins over the section's"
                )
                assert ("active" in anchor["class"]) == bool(link.get("active")), (
                    "only a link flagged active is marked active"
                )
        assert soup.select_one("[data-doc-search-root]") is None, (
            "search=false drops the widget"
        )


class TestPreviewPagesAndTokens:
    """The forthcoming preview pages and the chip modifier they rely on."""

    @pytest.mark.parametrize(
        ("template", "slug"),
        [
            ("pages/forthcoming-linter.jinja", "forthcoming/linter"),
            (
                "pages/forthcoming-testing-framework.jinja",
                "forthcoming/testing-framework",
            ),
        ],
    )
    def test_preview_sidebar_is_labelled_and_marks_itself(
        self, tmp_path: Path, template: str, slug: str
    ) -> None:
        """The preview sidebar names itself and nests anchors under the page."""
        soup = _render_page(tmp_path, template, slug)
        nav = soup.select_one("#sidebar nav[aria-label='Preview pages']")

        assert nav is not None, "the preview sidebar carries its nav_label"
        headings = [h.get_text(strip=True) for h in nav.select("h3")]
        assert headings == ["Forthcoming", "Sources"], "the preview groups"
        links = nav.select("a.sidebar-link")
        active = [a for a in links if "active" in a["class"]]
        assert len(active) == 1, "exactly one preview is active"
        assert active[0]["href"] == f"/netsuke/{slug}/", "the page marks itself"
        index = links.index(active[0])
        anchors = [a for a in links[index + 1 :] if "sidebar-link--sub" in a["class"]]
        assert anchors, "the preview lists its section anchors"
        assert all(str(a["href"]).startswith("#") for a in anchors), (
            "anchors are in-page"
        )
        assert soup.select_one("nav[aria-label='Breadcrumb'] [aria-current]"), (
            "the preview page carries the shared breadcrumb"
        )

    def test_docs_sidebar_default_headings(self, tmp_path: Path) -> None:
        """A docs page renders the three shared groups from docs_groups."""
        soup = _render_page(tmp_path, "pages/docs-cli.jinja", "docs/cli")
        headings = [h.get_text(strip=True) for h in soup.select("#sidebar h3")]

        assert headings == ["Introduction", "Core Concepts", "Reference"], (
            "the default groups come from docs_groups in order"
        )

    def test_accent_chip_is_a_named_modifier(self) -> None:
        """The vermillion chip the Design example uses exists in the stylesheet."""
        stylesheet = Path("src/styles/netsuke/himotoshi.css").read_text(
            encoding="utf-8"
        )
        rule = re.search(r"\.hm-chip--accent\s*\{([^}]*)\}", stylesheet)

        assert rule is not None, "the accent modifier is defined"
        assert "var(--netsuke-vermillion)" in rule.group(1), (
            "the accent chip draws from the vermillion token, not a literal"
        )
        assert "#" not in rule.group(1), "no arbitrary colour in the modifier"
