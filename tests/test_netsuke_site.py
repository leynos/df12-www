"""Integration tests for the Netsuke sub-site as configured in ``pages.yaml``.

The Netsuke content pages route through ``config/pages.yaml`` and render from
``templates/netsuke/``. These tests load the real configuration, render the
sub-site's content pages into a temporary directory, and assert the properties
that the v0.1.0-beta3 refresh introduced and that nothing else checks: the
forthcoming-capability routes exist, every page carries the configured release
version rather than a stale literal, no Jinja artefact leaks into the output,
and the forthcoming pages light up the Roadmap navigation item through the
``nav_href`` override.

Usage
-----
Run ``pytest tests/test_netsuke_site.py -v`` or ``make test``.
"""

from __future__ import annotations

import re
import typing as typ
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from df12_pages.config import load_site_config
from df12_pages.content_page import ContentPageGenerator

if typ.TYPE_CHECKING:
    from df12_pages.config.models import SubSiteConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGES_YAML = REPO_ROOT / "config" / "pages.yaml"

FORTHCOMING_SLUGS = (
    "forthcoming",
    "forthcoming/linter",
    "forthcoming/testing-framework",
)

# Text that only reaches the output when a `{% raw %}` block or a template
# variable was mishandled.
JINJA_ARTEFACT = re.compile(r"\{%\s*(?:raw|endraw)\s*%\}|\{\{\s*netsuke_version\s*\}\}")


@pytest.fixture(scope="module")
def netsuke() -> SubSiteConfig:
    """Load the Netsuke sub-site configuration from the real ``pages.yaml``."""
    return load_site_config(PAGES_YAML).sites["netsuke"]


@pytest.fixture(scope="module")
def rendered(
    netsuke: SubSiteConfig, tmp_path_factory: pytest.TempPathFactory
) -> dict[str, BeautifulSoup]:
    """Render every Netsuke content page into a temporary output tree."""
    out = tmp_path_factory.mktemp("netsuke")
    pages: dict[str, BeautifulSoup] = {}
    for cp in netsuke.content_pages:
        path = ContentPageGenerator(
            cp,
            out,
            templates_dir=netsuke.templates_dir,
            nav_links=netsuke.nav_links,
            stylesheet=netsuke.stylesheet,
            parent_link=netsuke.parent_link,
            base_path=netsuke.base_path,
            template_vars=netsuke.template_vars,
        ).run()
        assert path == out / cp.output_slug / "index.html"
        pages[cp.output_slug] = BeautifulSoup(
            path.read_text(encoding="utf-8"), "html.parser"
        )
    return pages


def _current_nav_labels(soup: BeautifulSoup) -> set[str]:
    """Return the labels of nav links marked ``aria-current="page"``."""
    selector = 'nav[aria-label="Primary navigation"] a[aria-current="page"]'
    return {anchor.get_text(strip=True) for anchor in soup.select(selector)}


class TestForthcomingRoutes:
    """The forthcoming-capability pages are routed, titled, and navigable."""

    def test_config_routes_every_forthcoming_page(self, netsuke: SubSiteConfig) -> None:
        """``pages.yaml`` registers the hub and both preview pages."""
        slugs = {cp.output_slug for cp in netsuke.content_pages}
        assert set(FORTHCOMING_SLUGS) <= slugs

    @pytest.mark.parametrize(
        ("slug", "title"),
        [
            ("forthcoming", "Forthcoming Capabilities"),
            ("forthcoming/linter", "Netsukefile Linter"),
            ("forthcoming/testing-framework", "Netsukefile Testing Framework"),
        ],
    )
    def test_forthcoming_page_renders_with_expected_title(
        self, rendered: dict[str, BeautifulSoup], slug: str, title: str
    ) -> None:
        """Each forthcoming page has the expected ``<h1>`` and one main landmark."""
        soup = rendered[slug]
        heading = soup.select_one("main h1")
        assert heading is not None
        assert heading.get_text(strip=True) == title
        assert len(soup.select("main")) == 1

    def test_forthcoming_pages_mark_roadmap_current(
        self, rendered: dict[str, BeautifulSoup]
    ) -> None:
        """The ``nav_href`` override lights up Roadmap on every forthcoming page."""
        for slug in FORTHCOMING_SLUGS:
            assert _current_nav_labels(rendered[slug]) == {"Roadmap"}, slug

    def test_hub_links_both_previews(self, rendered: dict[str, BeautifulSoup]) -> None:
        """The hub, the docs hub, and the roadmap all link to both previews."""
        for slug in ("forthcoming", "docs", "roadmap"):
            hrefs = {a["href"] for a in rendered[slug].select("main a[href]")}
            assert "/netsuke/forthcoming/linter/" in hrefs, slug
            assert "/netsuke/forthcoming/testing-framework/" in hrefs, slug


class TestReleaseAlignment:
    """Every page reflects the configured release and renders cleanly."""

    def test_configured_version_is_the_beta3_release(
        self, netsuke: SubSiteConfig
    ) -> None:
        """The single source of truth names the current release."""
        assert netsuke.template_vars["netsuke_version"] == "0.1.0-beta3"

    def test_no_page_leaks_jinja_artefacts(
        self, rendered: dict[str, BeautifulSoup]
    ) -> None:
        """No rendered page contains a raw tag or an unrendered version variable."""
        leaks = {
            slug for slug, soup in rendered.items() if JINJA_ARTEFACT.search(str(soup))
        }
        assert not leaks

    @pytest.mark.parametrize(
        "slug", ["install", "roadmap", "forthcoming", "forthcoming/linter"]
    )
    def test_release_pages_show_the_configured_version(
        self, rendered: dict[str, BeautifulSoup], netsuke: SubSiteConfig, slug: str
    ) -> None:
        """Pages that quote the release render the configured version."""
        text = rendered[slug].get_text(" ")
        assert f"v{netsuke.template_vars['netsuke_version']}" in text

    def test_no_page_mentions_the_superseded_version_as_current(
        self, rendered: dict[str, BeautifulSoup]
    ) -> None:
        """The release card and pills never fall back to the beta2 literal."""
        for slug in ("install", "roadmap"):
            kickers = rendered[slug].select(".hm-kicker")
            pills = " ".join(el.get_text(" ") for el in kickers)
            assert "beta2" not in pills, slug

    def test_kicker_labels_are_not_double_escaped(
        self, rendered: dict[str, BeautifulSoup]
    ) -> None:
        """Entity text such as ``&middot;`` never appears literally in a pill."""
        for slug, soup in rendered.items():
            for pill in soup.select(".hm-kicker"):
                assert "&middot;" not in pill.get_text()
                assert "&amp;" not in pill.get_text(), slug
