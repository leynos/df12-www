"""Load site configuration YAML into typed dataclasses."""

from __future__ import annotations

import dataclasses as dc
import typing as typ
from pathlib import Path

from ruamel.yaml import YAML

from .helpers import (
    DEFAULT_DOC_PATH,
    _build_repo_url,
    _build_theme_config,
    _default_manifest_path,
    _merge_layouts,
    _merge_theme,
    _parse_timestamp,
)
from .homepage import _build_homepage_config
from .about import _build_about_config
from .models import PageConfig, SiteConfig, SiteConfigError, ThemeConfig


def load_site_config(path: Path) -> SiteConfig:
    """Load the YAML configuration describing page and site layout choices.

    Parameters
    ----------
    path : Path
        Filesystem path to the YAML layout configuration file (for example,
        ``pages.yaml``).

    Returns
    -------
    SiteConfig
        Parsed site configuration, including page definitions, default theme,
        docs index output path, and optional homepage configuration.

    Raises
    ------
    FileNotFoundError
        If the configuration file does not exist at ``path``.
    TypeError
        If the top-level YAML structure is not a mapping.
    SiteConfigError
        If required sections or fields are missing or invalid in the
        configuration (for example, no pages are defined).
    YAMLError
        If the YAML content cannot be parsed by the underlying loader.

    Examples
    --------
    Load a site configuration from the default layout file:

    >>> from pathlib import Path
    >>> from df12_pages.config import load_site_config
    >>> config = load_site_config(Path("pages.yaml"))
    >>> sorted(config.pages.keys())[:1]
    ['getting-started']
    """
    if not path.exists():
        msg = f"Configuration file '{path}' not found."
        raise FileNotFoundError(msg)

    loader = YAML(typ="safe")
    loader.version = (1, 2)
    with path.open("r", encoding="utf-8") as handle:
        loaded = loader.load(handle) or {}
    if not isinstance(loaded, dict):  # pragma: no cover - config error guard
        msg = "Top-level YAML structure must be a mapping."
        raise TypeError(msg)
    raw: dict[str, typ.Any] = dict(loaded)
    defaults = raw.get("defaults", {}) or {}
    homepage_raw = raw.get("homepage")

    default_theme = _build_theme_config(defaults.get("theme", {}) or {})
    default_output_dir = Path(defaults.get("output_dir", "public"))
    default_filename_prefix = defaults.get("filename_prefix", "docs-")
    default_pygments_style = defaults.get("pygments_style", "monokai")
    default_page_title_suffix = defaults.get("page_title_suffix", "Docs")
    default_source_label = defaults.get("source_label", "Source material")
    default_footer_note = defaults.get("footer_note", "")
    default_page = defaults.get("default_page")
    default_branch = defaults.get("branch", "main")
    default_doc_path = defaults.get("doc_path", DEFAULT_DOC_PATH)
    default_repo = defaults.get("repo")
    default_language = defaults.get("language")
    docs_index_output = Path(defaults.get("docs_index_output", "public/docs.html"))

    shared_layouts = raw.get("layouts", {}) or {}
    pages_raw = raw.get("pages") or {}
    if not pages_raw:
        msg = "No pages defined in layout configuration."
        raise SiteConfigError(msg)

    page_defaults = _PageDefaults(
        theme=default_theme,
        output_dir=default_output_dir,
        filename_prefix=default_filename_prefix,
        pygments_style=default_pygments_style,
        page_title_suffix=default_page_title_suffix,
        source_label=default_source_label,
        footer_note=default_footer_note,
        branch=default_branch,
        doc_path=default_doc_path,
        repo=default_repo,
        language=default_language,
        shared_layouts=shared_layouts,
    )

    pages: dict[str, PageConfig] = {}
    for key, payload in pages_raw.items():
        match payload:
            case dict():
                pages[key] = _build_page_config(
                    key=key,
                    payload=payload,
                    defaults=page_defaults,
                )
            case _:
                continue

    homepage_config = _build_homepage_config(homepage_raw) if homepage_raw else None
    about_config = _build_about_config(
        raw.get("about"), fallback_footer=homepage_config.footer if homepage_config else None
    )

    return SiteConfig(
        pages=pages,
        default_page=default_page,
        docs_index_output=docs_index_output,
        theme=default_theme,
        homepage=homepage_config,
        about=about_config,
    )


@dc.dataclass(slots=True)
class _PageDefaults:
    """Internal container for page default configuration values."""

    theme: ThemeConfig
    output_dir: Path
    filename_prefix: str
    pygments_style: str
    page_title_suffix: str
    source_label: str
    footer_note: str
    branch: str
    doc_path: str
    repo: str | None
    language: str | None
    shared_layouts: typ.Mapping[str, typ.Any]


def _build_page_config(
    *,
    key: str,
    payload: typ.Mapping[str, typ.Any],
    defaults: _PageDefaults,
) -> PageConfig:
    """Build a PageConfig for a single page entry using defaults and overrides."""
    repo = payload.get("repo", defaults.repo)
    branch = payload.get("branch", defaults.branch)
    language = payload.get("language", defaults.language)
    doc_path = payload.get("doc_path", defaults.doc_path)
    source_url = payload.get("source_url")
    if not source_url and repo:
        source_url = _build_repo_url(repo, branch, doc_path)
    if not source_url:
        msg = f"Page '{key}' is missing 'source_url' or 'repo'."
        raise SiteConfigError(msg)

    label = payload.get("label") or key.replace("-", " ").title()
    source_label = payload.get("source_label", defaults.source_label)
    title_suffix = payload.get("page_title_suffix", defaults.page_title_suffix)
    filename_prefix = payload.get("filename_prefix", defaults.filename_prefix)
    output_dir = Path(payload.get("output_dir", defaults.output_dir))
    pygments_style = payload.get("pygments_style", defaults.pygments_style)
    footer_note = payload.get("footer_note", defaults.footer_note)
    theme = _merge_theme(defaults.theme, payload.get("theme"))

    layouts = _merge_layouts(defaults.shared_layouts, payload.get("layouts"))

    manifest_url = payload.get("manifest_url")
    if not manifest_url and repo:
        manifest_path = payload.get("manifest_path") or _default_manifest_path(language)
        if manifest_path:
            manifest_url = _build_repo_url(repo, branch, manifest_path)

    description_override = payload.get("description")
    latest_release = payload.get("latest_release")
    latest_release_published_at = _parse_timestamp(
        payload.get("latest_release_published_at")
    )

    return PageConfig(
        key=key,
        label=label,
        source_url=source_url,
        source_label=source_label,
        page_title_suffix=title_suffix,
        filename_prefix=filename_prefix,
        output_dir=output_dir,
        pygments_style=pygments_style,
        footer_note=footer_note,
        theme=theme,
        layouts=layouts,
        repo=repo,
        branch=branch,
        language=language.lower() if isinstance(language, str) else language,
        manifest_url=manifest_url,
        description_override=description_override,
        doc_path=doc_path,
        latest_release=latest_release,
        latest_release_published_at=latest_release_published_at,
    )


__all__ = ["load_site_config"]
