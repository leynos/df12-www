"""Regression tests for shared-content page generation."""

from __future__ import annotations

import typing as typ

from bs4 import BeautifulSoup

from df12_pages.config import SharedContentConfig
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
