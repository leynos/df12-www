"""Tests for documentation generation layout and navigation."""

from __future__ import annotations

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from df12_pages.config import PageConfig, ThemeConfig
from df12_pages.generator import PageContentGenerator


@pytest.fixture(scope="module")
def sample_markdown() -> str:
    return (
        "## 1. Introduction\n"
        "### Overview\n"
        "Intro details.\n\n"
        "**Capabilities**\n"
        "Bullet list of capabilities.\n\n"
        "## 2. Getting Started\n"
        "### Install\n"
        "Install steps here.\n\n"
        "### Configure\n"
        "Configuration steps here.\n"
    )


@pytest.fixture(scope="module")
def page_config(tmp_path_factory: pytest.TempPathFactory) -> PageConfig:
    output_dir = tmp_path_factory.mktemp("docs")
    theme = ThemeConfig(
        hero_eyebrow="Fixture",
        hero_tagline="Fixture tagline",
        doc_label="Docs",
        site_name="df12",
    )
    return PageConfig(
        key="test",
        label="Test Docs",
        source_url="https://example.invalid/docs.md",
        source_label="Fixture Source",
        page_title_suffix="Fixture",
        filename_prefix="docs-test-",
        output_dir=output_dir,
        pygments_style="monokai",
        footer_note="",
        theme=theme,
        layouts={},
        repo=None,
        branch="main",
        language=None,
        manifest_url=None,
        description_override=None,
    )


@pytest.fixture()
def generated_docs(
    sample_markdown: str,
    page_config: PageConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, BeautifulSoup]:
    monkeypatch.setattr(
        PageContentGenerator,
        "_fetch_markdown",
        lambda self: sample_markdown,
        raising=False,
    )
    generator = PageContentGenerator(page_config)
    written_paths = generator.run()
    docs: dict[str, BeautifulSoup] = {}
    for path in written_paths:
        html = path.read_text(encoding="utf-8")
        docs[path.name] = BeautifulSoup(html, "html.parser")
    return docs


def test_sidebar_groups_include_top_and_child_links(generated_docs: dict[str, BeautifulSoup]) -> None:
    soup = generated_docs["docs-test-introduction.html"]
    groups = soup.select(".doc-sidebar__groups .doc-nav-group")
    assert [g.select_one("h3").get_text(strip=True) for g in groups] == [
        "Introduction",
        "Getting Started",
    ]

    intro_links = [a["href"] for a in groups[0].select("a")]
    assert intro_links[0].endswith("docs-test-introduction.html")
    assert "#introduction-overview" in intro_links[1]
    assert "#introduction-capabilities" in intro_links[2]


def test_only_one_sidebar_link_flagged_active(generated_docs: dict[str, BeautifulSoup]) -> None:
    soup = generated_docs["docs-test-getting-started.html"]
    active_links = soup.select(".doc-nav__link[aria-current='page']")
    assert len(active_links) == 1
    assert active_links[0]["href"].endswith("docs-test-getting-started.html")


def test_bold_heading_promoted_to_nav_entry(generated_docs: dict[str, BeautifulSoup]) -> None:
    soup = generated_docs["docs-test-introduction.html"]
    nav_labels = [span.get_text(strip=True) for span in soup.select(".doc-nav__list a span")]
    assert any(label == "Capabilities" for label in nav_labels)
