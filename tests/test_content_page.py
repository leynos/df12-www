"""Tests for the ContentPageGenerator."""

from __future__ import annotations

import typing as typ

from df12_pages.config import ContentPageConfig, NavLinkConfig
from df12_pages.content_page import ContentPageGenerator

if typ.TYPE_CHECKING:
    from pathlib import Path

_BASE_TEMPLATE = """\
<!DOCTYPE html><html lang="en"><head>
<link rel="stylesheet" href="../{{ stylesheet }}">
</head><body>
<nav>
{% for link in nav_links %}
<a href="{{ link.href }}"
{%- if link.current %} aria-current="page"{% endif %}>{{ link.label }}</a>
{% endfor %}
</nav>
{% block hero %}{% endblock %}
{% block route_map %}{% endblock %}
{% block content %}{% endblock %}
{% block footer_cta %}{% endblock %}
</body></html>
"""

_CHILD_TEMPLATE = """\
{% extends "doc_page.jinja" %}
{% block content %}<p>Hello from demo</p>{% endblock %}
"""


def _write_templates(templates_dir: Path) -> None:
    templates_dir.mkdir(parents=True, exist_ok=True)
    (templates_dir / "doc_page.jinja").write_text(_BASE_TEMPLATE, encoding="utf-8")
    pages_dir = templates_dir / "pages"
    pages_dir.mkdir()
    (pages_dir / "demo.jinja").write_text(_CHILD_TEMPLATE, encoding="utf-8")


def _make_nav() -> list[NavLinkConfig]:
    return [
        NavLinkConfig(label="Home", href="../"),
        NavLinkConfig(label="Demo", href="../demo/"),
        NavLinkConfig(label="Other", href="../other/"),
    ]


def test_output_path(tmp_path: Path) -> None:
    """run() returns output_dir/slug/index.html and the file exists."""
    templates_dir = tmp_path / "templates"
    _write_templates(templates_dir)
    output_dir = tmp_path / "out"
    config = ContentPageConfig(
        key="demo", label="Demo", template="pages/demo.jinja", output_slug="demo"
    )
    result = ContentPageGenerator(
        config,
        output_dir,
        templates_dir=templates_dir,
        nav_links=_make_nav(),
        stylesheet="assets/site.css",
    ).run()
    assert result == output_dir / "demo" / "index.html"
    assert result.exists()


def test_nav_current_marking(tmp_path: Path) -> None:
    """Active page gets aria-current='page' and href rewritten to './'."""
    templates_dir = tmp_path / "templates"
    _write_templates(templates_dir)
    output_dir = tmp_path / "out"
    config = ContentPageConfig(
        key="demo", label="Demo", template="pages/demo.jinja", output_slug="demo"
    )
    result = ContentPageGenerator(
        config,
        output_dir,
        templates_dir=templates_dir,
        nav_links=_make_nav(),
        stylesheet="assets/site.css",
    ).run()
    html = result.read_text(encoding="utf-8")
    assert 'aria-current="page"' in html
    assert 'href="./"' in html
    # Home link should NOT be marked current
    assert 'href="../"' in html


def test_stylesheet_passthrough(tmp_path: Path) -> None:
    """Stylesheet variable reaches the template's <link> tag."""
    templates_dir = tmp_path / "templates"
    _write_templates(templates_dir)
    output_dir = tmp_path / "out"
    config = ContentPageConfig(
        key="demo", label="Demo", template="pages/demo.jinja", output_slug="demo"
    )
    result = ContentPageGenerator(
        config,
        output_dir,
        templates_dir=templates_dir,
        nav_links=_make_nav(),
        stylesheet="assets/custom.css",
    ).run()
    html = result.read_text(encoding="utf-8")
    assert "assets/custom.css" in html


def test_trailing_newline(tmp_path: Path) -> None:
    """Output ends with a newline."""
    templates_dir = tmp_path / "templates"
    _write_templates(templates_dir)
    output_dir = tmp_path / "out"
    config = ContentPageConfig(
        key="demo", label="Demo", template="pages/demo.jinja", output_slug="demo"
    )
    result = ContentPageGenerator(
        config,
        output_dir,
        templates_dir=templates_dir,
        nav_links=_make_nav(),
        stylesheet="assets/site.css",
    ).run()
    html = result.read_text(encoding="utf-8")
    assert html.endswith("\n")


def test_template_content(tmp_path: Path) -> None:
    """Child template block content appears in rendered output."""
    templates_dir = tmp_path / "templates"
    _write_templates(templates_dir)
    output_dir = tmp_path / "out"
    config = ContentPageConfig(
        key="demo", label="Demo", template="pages/demo.jinja", output_slug="demo"
    )
    result = ContentPageGenerator(
        config,
        output_dir,
        templates_dir=templates_dir,
        nav_links=_make_nav(),
        stylesheet="assets/site.css",
    ).run()
    html = result.read_text(encoding="utf-8")
    assert "<p>Hello from demo</p>" in html
