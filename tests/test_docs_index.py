"""Unit tests for docs index helpers."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from df12_pages.config import PageConfig, ThemeConfig
from df12_pages.docs_index import _build_package_url


def _base_page(
    *,
    latest_release: str | None = "v1.0.0",
    overrides: Mapping[str, Any] | None = None,
) -> PageConfig:
    """Construct a minimal PageConfig fixture for docs index tests."""

    base_kwargs: dict[str, Any] = {
        "key": "test",
        "label": "Test",
        "source_url": "https://example.invalid/docs.md",
        "source_label": "src",
        "page_title_suffix": "suffix",
        "filename_prefix": "docs-test-",
        "output_dir": Path("tmp"),
        "pygments_style": "monokai",
        "footer_note": "",
        "theme": ThemeConfig("eyebrow", "tagline", "Docs", "df12"),
        "layouts": {},
        "repo": "owner/pkg",
        "branch": "main",
        "language": "rust",
        "manifest_url": None,
        "description_override": None,
        "doc_path": "docs.md",
        "latest_release": latest_release,
        "latest_release_published_at": None,
    }
    if overrides:
        base_kwargs.update(overrides)
    return PageConfig(**base_kwargs)


def test_package_url_requires_release() -> None:
    page = _base_page(latest_release=None)
    assert (
        _build_package_url(page) is None
    ), "Expected None when latest_release is absent"


def test_package_url_present_for_rust_release() -> None:
    page = _base_page()
    actual = _build_package_url(page)
    assert (
        actual == "https://crates.io/crates/pkg"
    ), f"Expected crates.io URL for rust releases, got {actual!r}"
