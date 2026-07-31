"""Regression tests for sub-site homepage rendering."""

from __future__ import annotations

import typing as typ

from bs4 import BeautifulSoup

from df12_pages.config import SubSiteHomepageConfig
from df12_pages.subsite_homepage import SubSiteHomePageBuilder

if typ.TYPE_CHECKING:
    from pathlib import Path

MANIFEST_FRAGMENT = 'netsuke_version: "1.0.0"\nrules:\n  - name: compile\n'


def test_subsite_homepage_preserves_configured_title(tmp_path: Path) -> None:
    """Freeform context must not override fixed homepage metadata."""
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "home_page.jinja").write_text(
        "<title>{{ homepage.title }}</title><p>{{ generated_at.isoformat() }}</p>",
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


def test_subsite_homepage_environment_registers_highlight_tag(
    tmp_path: Path,
) -> None:
    """The builder's Jinja environment renders ``{% highlight %}`` blocks."""
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "home_page.jinja").write_text(
        "{% highlight 'netsuke' %}{% raw %}\n"
        + MANIFEST_FRAGMENT
        + "{% endraw %}{% endhighlight %}\n",
        encoding="utf-8",
    )

    config = SubSiteHomepageConfig(
        output=tmp_path / "index.html",
        title="Highlighted homepage",
        context={},
    )

    output = SubSiteHomePageBuilder(config, templates_dir=template_dir).run()

    soup = BeautifulSoup(output.read_text(encoding="utf-8"), "html.parser")
    block = soup.find("div", class_="hm-syntax")
    assert block is not None, "highlight tag should emit a .hm-syntax wrapper"
    assert block.find("span", class_="nt") is not None, "YAML keys should be .nt"
    assert block.get_text().strip() == MANIFEST_FRAGMENT.strip(), (
        "highlighted source text should round-trip unchanged"
    )
