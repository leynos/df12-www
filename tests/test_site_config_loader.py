"""Regression tests for configuration loader path handling."""

from __future__ import annotations

import typing as typ

import pytest

from df12_pages.config import SiteConfigError, load_site_config

if typ.TYPE_CHECKING:
    from pathlib import Path


def test_shared_content_sources_resolve_relative_to_config_file(tmp_path: Path) -> None:
    """Relative shared-content sources should anchor to the YAML file location."""
    config_dir = tmp_path / "config"
    shared_dir = config_dir / "shared"
    shared_dir.mkdir(parents=True)
    source = shared_dir / "privacy.md"
    source.write_text("# Privacy Policy\n", encoding="utf-8")

    pages_yaml = config_dir / "pages.yaml"
    pages_yaml.write_text(
        """
defaults:
  docs_index_output: public/docs.html
pages:
  getting-started:
    title: Getting started
    output: public/getting-started.html
    source_url: https://example.com/guide.md
shared_content:
  privacy-policy:
    label: Privacy Policy
    source: shared/privacy.md
    output_slug: privacy-policy
""".lstrip(),
        encoding="utf-8",
    )

    config = load_site_config(pages_yaml)

    assert config.shared_content["privacy-policy"].source == str(source)


_SITE_YAML_PREFIX = """\
defaults:
  docs_index_output: public/docs.html
pages:
  getting-started:
    source_url: https://example.com/guide.md
sites:
  demo:
    output_dir: public/demo
    templates_dir: templates/demo
    stylesheet: assets/demo.css
"""


def test_content_pages_parsed(tmp_path: Path) -> None:
    """YAML with content_pages list produces populated SubSiteConfig."""
    pages_yaml = tmp_path / "pages.yaml"
    pages_yaml.write_text(
        _SITE_YAML_PREFIX
        + """\
    content_pages:
      - key: arch
        template: pages/arch.jinja
        label: Architecture
        output_slug: architecture
      - key: proto
        template: pages/proto.jinja
""",
        encoding="utf-8",
    )
    config = load_site_config(pages_yaml)
    cp = config.sites["demo"].content_pages
    assert len(cp) == 2  # noqa: PLR2004
    assert cp[0].key == "arch"
    assert cp[0].label == "Architecture"
    assert cp[0].template == "pages/arch.jinja"
    assert cp[0].output_slug == "architecture"
    # Defaults
    assert cp[1].label == "Proto"
    assert cp[1].output_slug == "proto"


def test_content_pages_missing_key_raises(tmp_path: Path) -> None:
    """Entry without 'key' raises SiteConfigError."""
    pages_yaml = tmp_path / "pages.yaml"
    pages_yaml.write_text(
        _SITE_YAML_PREFIX
        + """\
    content_pages:
      - template: pages/demo.jinja
""",
        encoding="utf-8",
    )
    with pytest.raises(SiteConfigError, match="requires"):
        load_site_config(pages_yaml)


def test_content_pages_missing_template_raises(tmp_path: Path) -> None:
    """Entry without 'template' raises SiteConfigError."""
    pages_yaml = tmp_path / "pages.yaml"
    pages_yaml.write_text(
        _SITE_YAML_PREFIX
        + """\
    content_pages:
      - key: demo
""",
        encoding="utf-8",
    )
    with pytest.raises(SiteConfigError, match="requires"):
        load_site_config(pages_yaml)


def test_content_pages_defaults(tmp_path: Path) -> None:
    """Missing label defaults to titlecased key; missing output_slug defaults to key."""
    pages_yaml = tmp_path / "pages.yaml"
    pages_yaml.write_text(
        _SITE_YAML_PREFIX
        + """\
    content_pages:
      - key: database-backends
        template: pages/db.jinja
""",
        encoding="utf-8",
    )
    config = load_site_config(pages_yaml)
    cp = config.sites["demo"].content_pages[0]
    assert cp.label == "Database Backends"
    assert cp.output_slug == "database-backends"


def test_page_category_defaults_to_tool(tmp_path: Path) -> None:
    """Pages without an explicit category fall back to the 'tool' default."""
    pages_yaml = tmp_path / "pages.yaml"
    pages_yaml.write_text(
        """\
defaults:
  docs_index_output: public/docs.html
pages:
  getting-started:
    source_url: https://example.com/guide.md
""",
        encoding="utf-8",
    )
    config = load_site_config(pages_yaml)
    assert config.pages["getting-started"].category == "tool"


def test_page_category_parsed_and_default_overridable(tmp_path: Path) -> None:
    """Explicit page categories win over the defaults-level category."""
    pages_yaml = tmp_path / "pages.yaml"
    pages_yaml.write_text(
        """\
defaults:
  docs_index_output: public/docs.html
  category: library
pages:
  getting-started:
    source_url: https://example.com/guide.md
  helper:
    source_url: https://example.com/helper.md
    category: skill
""",
        encoding="utf-8",
    )
    config = load_site_config(pages_yaml)
    assert config.pages["getting-started"].category == "library"
    assert config.pages["helper"].category == "skill"


def test_page_category_invalid_raises(tmp_path: Path) -> None:
    """An unknown category value fails loading with a clear error."""
    pages_yaml = tmp_path / "pages.yaml"
    pages_yaml.write_text(
        """\
defaults:
  docs_index_output: public/docs.html
pages:
  getting-started:
    source_url: https://example.com/guide.md
    category: gadget
""",
        encoding="utf-8",
    )
    with pytest.raises(SiteConfigError, match="unknown category 'gadget'"):
        load_site_config(pages_yaml)
