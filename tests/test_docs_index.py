"""Unit tests for docs index helpers.

These tests cover the internal helpers that build package URLs for the docs
index cards. They focus on ensuring crates.io links are emitted when releases
are present and omitted otherwise.

Usage
-----
Run ``pytest tests/test_docs_index.py -v`` or ``make test`` to execute the
suite. No special fixtures are required beyond pytest's built-in ``tmp_path``.

Examples
--------
- ``test_package_url_requires_release`` verifies ``_build_package_url`` returns
  ``None`` when ``latest_release`` is unset.
- ``test_package_url_present_for_rust_release`` asserts that Rust pages produce
  a ``https://crates.io/crates/<name>`` link when ``latest_release`` is set.
"""

from __future__ import annotations

import typing as typ

from df12_pages.config import PageConfig, SiteConfig, ThemeConfig
from df12_pages.docs_index import (
    DocsIndexBuilder,
    _build_package_url,
    _group_entries_by_category,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path


def _base_page(
    tmp_path: Path,
    *,
    latest_release: str | None = "v1.0.0",
    overrides: cabc.Mapping[str, typ.Any] | None = None,
) -> PageConfig:
    """Construct a minimal PageConfig fixture for docs index tests."""
    output_dir = tmp_path / "docs"
    output_dir.mkdir(parents=True, exist_ok=True)
    page = PageConfig(
        key="test",
        label="Test",
        source_url="https://example.invalid/docs.md",
        source_label="src",
        page_title_suffix="suffix",
        filename_prefix="docs-test-",
        output_dir=output_dir,
        pygments_style="monokai",
        footer_note="",
        theme=ThemeConfig("eyebrow", "tagline", "Docs", "df12"),
        layouts={},
        repo="owner/pkg",
        branch="main",
        language="rust",
        manifest_url=None,
        description_override=None,
        doc_path="docs.md",
        latest_release=latest_release,
        latest_release_published_at=None,
    )
    if overrides:
        for key, value in overrides.items():
            setattr(page, key, value)
    return page


def test_package_url_requires_release(tmp_path: Path) -> None:
    """Package URL should be omitted when no latest release is configured."""
    page = _base_page(tmp_path, latest_release=None)
    assert _build_package_url(page) is None, (
        "Expected None when latest_release is absent"
    )


def test_package_url_present_for_rust_release(tmp_path: Path) -> None:
    """Package URL should be populated for Rust releases."""
    page = _base_page(tmp_path)
    actual = _build_package_url(page)
    assert actual == "https://crates.io/crates/pkg", (
        f"Expected crates.io URL for rust releases, got {actual!r}"
    )


def test_group_entries_by_category_orders_and_omits_empty() -> None:
    """Sections follow PAGE_CATEGORIES order and skip empty categories."""
    entries: list[dict[str, str | None]] = [
        {"label": "Lib", "category": "library"},
        {"label": "Tool", "category": "tool"},
        {"label": "Skill", "category": "skill"},
        {"label": "Tool 2", "category": "tool"},
    ]
    sections = _group_entries_by_category(entries)
    assert [section["title"] for section in sections] == [
        "Tools",
        "Libraries",
        "Skills",
    ]
    tools = sections[0]["entries"]
    assert [entry["label"] for entry in tools] == ["Tool", "Tool 2"]
    assert all(section["anchor"] for section in sections)


def test_gather_entries_carries_category(tmp_path: Path) -> None:
    """Docs index entries expose the page category for template grouping."""
    page = _base_page(tmp_path, overrides={"category": "library"})
    (page.output_dir / "docs-test-introduction.html").write_text(
        "<html></html>", encoding="utf-8"
    )
    site = SiteConfig(
        pages={"test": page},
        docs_index_output=page.output_dir / "docs.html",
    )
    builder = DocsIndexBuilder(site)
    entries = builder._gather_entries()
    assert entries[0]["category"] == "library"
