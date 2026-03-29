"""Regression tests for configuration loader path handling."""

from __future__ import annotations

import typing as typ

from df12_pages.config import load_site_config

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
