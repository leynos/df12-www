"""Unit tests for docs index helpers."""

from __future__ import annotations

from pathlib import Path

from df12_pages.config import PageConfig, ThemeConfig
from df12_pages.docs_index import _build_package_url


def _base_page(**overrides):
    theme = ThemeConfig("eyebrow", "tagline", "Docs", "df12")
    page = PageConfig(
        key="test",
        label="Test",
        source_url="https://example.invalid/docs.md",
        source_label="src",
        page_title_suffix="suffix",
        filename_prefix="docs-test-",
        output_dir=Path("tmp"),
        pygments_style="monokai",
        footer_note="",
        theme=theme,
        layouts={},
        repo="owner/pkg",
        branch="main",
        language="rust",
        manifest_url=None,
        description_override=None,
        doc_path="docs.md",
        latest_release="v1.0.0",
        latest_release_published_at=None,
    )
    for key, value in overrides.items():
        setattr(page, key, value)
    return page


def test_package_url_requires_release() -> None:
    page = _base_page(latest_release=None)
    assert _build_package_url(page) is None


def test_package_url_present_for_rust_release() -> None:
    page = _base_page()
    assert _build_package_url(page) == "https://crates.io/crates/pkg"
