"""Regression tests for shared-content page generation."""

from __future__ import annotations

import typing as typ

from bs4 import BeautifulSoup

from df12_pages.config import SharedContentConfig, SharedContentPageChrome
from df12_pages.shared_content import SharedContentGenerator

if typ.TYPE_CHECKING:
    from pathlib import Path


def test_shared_content_uses_parent_relative_stylesheet_by_default(
    tmp_path: Path,
) -> None:
    """Root shared-content pages should use the absolute shared stylesheet."""
    source = tmp_path / "privacy-policy.md"
    source.write_text("# Privacy Policy\n\nBody copy.\n", encoding="utf-8")

    config = SharedContentConfig(
        key="privacy-policy",
        label="Privacy Policy",
        source=str(source),
        output_slug="privacy-policy",
    )

    output_path = SharedContentGenerator(config, tmp_path).run()
    soup = BeautifulSoup(output_path.read_text(encoding="utf-8"), "html.parser")

    stylesheet = soup.find("link", attrs={"href": "/assets/site.css"})
    assert stylesheet is not None
    assert stylesheet.get("href") == "/assets/site.css"
    assert [heading.get_text(strip=True) for heading in soup.find_all("h1")] == [
        "Privacy Policy"
    ]


def test_shared_content_exposes_subsite_template_vars(tmp_path: Path) -> None:
    """Sub-site shared pages receive the same globals as their content pages."""
    source = tmp_path / "privacy-policy.md"
    source.write_text("# Privacy Policy\n\nBody copy.\n", encoding="utf-8")
    template = tmp_path / "shared_content_page.jinja"
    template.write_text(
        '<a href="{{ repository_url }}">Episodic source repository</a>\n',
        encoding="utf-8",
    )
    config = SharedContentConfig(
        key="privacy-policy",
        label="Privacy Policy",
        source=str(source),
        output_slug="privacy-policy",
    )

    output_path = SharedContentGenerator(
        config,
        tmp_path,
        templates_dir=tmp_path,
        page_chrome=SharedContentPageChrome(
            template_vars={"repository_url": "https://github.com/leynos/episodic"}
        ),
    ).run()

    soup = BeautifulSoup(output_path.read_text(encoding="utf-8"), "html.parser")
    repository_link = soup.find("a")
    assert repository_link is not None, "shared page must render the repository link"
    assert repository_link.get("href") == "https://github.com/leynos/episodic", (
        "shared page must retain the configured repository URL"
    )


def test_structured_shared_content_renders_toc_sections_and_cards(
    tmp_path: Path,
) -> None:
    """Structured pages gain a TOC, section wrappers, and badge cards."""
    source = tmp_path / "privacy-policy.md"
    source.write_text(
        "# Privacy Policy\n"
        "\n"
        "## Contact details { #contact }\n"
        "\n"
        '!!! card "@"\n'
        "    ### Email\n"
        "\n"
        "    Write to us.\n"
        "\n"
        "## How to complain { #complain }\n"
        "\n"
        '!!! card accent "ICO"\n'
        "    ### The ICO's address\n"
        "\n"
        "    Wilmslow.\n"
        "\n"
        "## Last updated\n"
        "\n"
        "9 March 2026\n",
        encoding="utf-8",
    )

    config = SharedContentConfig(
        key="privacy-policy",
        label="Privacy Policy",
        source=str(source),
        output_slug="privacy-policy",
        sections=True,
        toc=True,
        toc_exclude=("Last updated",),
        divider_sections=("Last updated",),
    )

    output_path = SharedContentGenerator(config, tmp_path).run()
    soup = BeautifulSoup(output_path.read_text(encoding="utf-8"), "html.parser")

    toc = soup.find("nav", class_="content-toc")
    assert toc is not None, "structured page should render a content-toc nav"
    toc_targets = [link.get("href") for link in toc.find_all("a")]
    assert toc_targets == ["#contact", "#complain"], (
        "TOC should link each section except excluded titles"
    )

    section_ids = [section.get("id") for section in soup.find_all("section")]
    assert section_ids == ["contact", "complain", "last-updated"], (
        "each h2-delimited run should become a section with a slug id"
    )
    divider = soup.find("section", class_="content-section--divider")
    assert divider is not None, "divider_sections titles should gain the modifier"
    assert divider.get("id") == "last-updated", (
        "the divider modifier should apply to the configured section"
    )

    badges = [
        badge.get_text(strip=True)
        for badge in soup.find_all("div", class_="content-card__badge")
    ]
    assert badges == ["@", "ICO"], "card admonitions should render badge circles"
    accent_card = soup.find("div", class_="content-card--accent")
    assert accent_card is not None, "the accent card variant should style the ICO card"
    assert "admonition" not in output_path.read_text(encoding="utf-8"), (
        "admonition markup should be fully rewritten into card markup"
    )


def test_unstructured_shared_content_body_is_unchanged(tmp_path: Path) -> None:
    """Pages without structure flags or card markers render as before."""
    source = tmp_path / "terms.md"
    source.write_text(
        "# Terms\n\n## Scope\n\nPlain body copy.\n",
        encoding="utf-8",
    )

    config = SharedContentConfig(
        key="terms-of-use",
        label="Terms of Use",
        source=str(source),
        output_slug="terms-of-use",
    )

    output_path = SharedContentGenerator(config, tmp_path).run()
    soup = BeautifulSoup(output_path.read_text(encoding="utf-8"), "html.parser")

    assert soup.find("nav", class_="content-toc") is None, (
        "pages without toc enabled should not render a TOC"
    )
    assert soup.find("section") is None, (
        "pages without structure flags should not wrap sections"
    )
    heading = soup.find("h2")
    assert heading is not None, "the body headings should be preserved"
    assert heading.get_text(strip=True) == "Scope", (
        "the body heading text should pass through unchanged"
    )
