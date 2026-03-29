"""Regression tests for sub-site homepage rendering."""

from __future__ import annotations

import typing as typ

from df12_pages.config import SubSiteHomepageConfig
from df12_pages.subsite_homepage import SubSiteHomePageBuilder

if typ.TYPE_CHECKING:
    from pathlib import Path


def test_subsite_homepage_preserves_configured_title(tmp_path: Path) -> None:
    """Freeform context must not override fixed homepage metadata."""
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "home_page.jinja").write_text(
        "<title>{{ title }}</title><p>{{ generated_at.isoformat() }}</p>",
        encoding="utf-8",
    )

    config = SubSiteHomepageConfig(
        output=tmp_path / "index.html",
        title="Expected title",
        context={"title": "Wrong title"},
    )

    output = SubSiteHomePageBuilder(config, templates_dir=template_dir).run()
    html = output.read_text(encoding="utf-8")

    assert "<title>Expected title</title>" in html
