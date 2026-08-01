"""Tests for the Netsuke sub-site's data-driven navigation chrome.

The docs pages derive three pieces of navigation from the shared
``docs_pages`` list in ``templates/netsuke/docs_nav.jinja``: the mobile
sub-menu dropdown, and the footer previous/next links (via
``docs_footer``). Guides pages render the same footer structure through
``footer_nav`` with bespoke destinations. These tests render the real
page templates and assert the generated markup stays coherent with that
single source of truth.

Usage
-----
Run ``pytest tests/test_netsuke_navigation.py -v`` or ``make test``.
"""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from df12_pages.config import ContentPageConfig
from df12_pages.content_page import ContentPageGenerator

NETSUKE_TEMPLATES = "templates/netsuke"

DOCS_ORDER = [
    ("", "Documentation Hub"),
    ("getting-started", "Getting Started"),
    ("manifest-reference", "Manifest Reference"),
    ("rules-and-targets", "Rules & Targets"),
    ("templating", "Templating"),
    ("standard-library", "Standard Library"),
    ("cli", "CLI Commands"),
    ("configuration", "Configuration"),
    ("security", "Security Model"),
]


def _render(tmp_path: Path, template: str, output_slug: str) -> BeautifulSoup:
    """Render one Netsuke page template and parse the output."""
    config = ContentPageConfig(
        key=output_slug.replace("/", "-"),
        label=output_slug,
        template=template,
        output_slug=output_slug,
    )
    generator = ContentPageGenerator(
        config,
        tmp_path / "out",
        templates_dir=Path(NETSUKE_TEMPLATES).resolve(),
        nav_links=[],
        stylesheet="assets/css/himotoshi.css",
    )
    output_path = generator.run()
    return BeautifulSoup(output_path.read_text(encoding="utf-8"), "html.parser")


def _footer_links(soup: BeautifulSoup) -> list[tuple[str, str, str]]:
    """Return (kicker, label, href) for each footer navigation link."""
    links = []
    for anchor in soup.select("main a"):
        kicker = anchor.select_one(".uppercase.tracking-wide")
        label = anchor.select_one(".font-medium.text-sm")
        if kicker and label:
            links.append(
                (
                    kicker.get_text(strip=True),
                    label.get_text(strip=True),
                    anchor["href"],
                )
            )
    return links


class TestDocsNavigation:
    """The docs dropdown and footers derive from the shared page order."""

    def test_mobile_dropdown_lists_every_docs_page(self, tmp_path: Path) -> None:
        """The sub-menu offers all docs pages with the current one selected."""
        soup = _render(tmp_path, "pages/docs-templating.jinja", "docs/templating")
        options = soup.select("select[data-docs-nav-select] option")

        labels = [option.get_text(strip=True) for option in options]
        assert labels == [label for _, label in DOCS_ORDER], (
            "dropdown must list the docs pages in reading order"
        )

        selected = [o for o in options if o.has_attr("selected")]
        assert len(selected) == 1, "exactly one option should be pre-selected"
        assert selected[0].get_text(strip=True) == "Templating"

    def test_mid_chain_footer_links_neighbours(self, tmp_path: Path) -> None:
        """A mid-chain docs page links its list neighbours."""
        soup = _render(tmp_path, "pages/docs-templating.jinja", "docs/templating")
        links = _footer_links(soup)

        assert (
            "Previous",
            "Rules & Targets",
            "/netsuke/docs/rules-and-targets/",
        ) in links
        assert (
            "Next",
            "Standard Library",
            "/netsuke/docs/standard-library/",
        ) in links

    def test_final_docs_page_continues_to_examples(self, tmp_path: Path) -> None:
        """The last docs page hands over to the examples hub."""
        soup = _render(tmp_path, "pages/docs-security.jinja", "docs/security")
        links = _footer_links(soup)

        assert (
            "Previous",
            "Configuration",
            "/netsuke/docs/configuration/",
        ) in links
        assert ("Next", "Examples Hub", "/netsuke/examples/") in links


class TestGuidesFooter:
    """Guides pages share the footer structure with bespoke destinations."""

    def test_architecture_guide_footer(self, tmp_path: Path) -> None:
        """The architecture guide points back to guides and on to the docs."""
        soup = _render(
            tmp_path, "pages/guides-architecture.jinja", "guides/architecture"
        )
        links = _footer_links(soup)

        assert ("Back", "Guides", "/netsuke/guides/") in links
        assert (
            "Next",
            "Manifest Reference",
            "/netsuke/docs/manifest-reference/",
        ) in links
