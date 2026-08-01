"""Load site configuration YAML into typed dataclasses."""

from __future__ import annotations

import dataclasses as dc
import typing as typ
from pathlib import Path

from ruamel.yaml import YAML

from .about import _build_about_config
from .helpers import (
    DEFAULT_DOC_PATH,
    _build_repo_url,
    _build_theme_config,
    _default_manifest_path,
    _merge_layouts,
    _merge_theme,
    _optional_str,
    _parse_timestamp,
)
from .homepage import _build_homepage_config, _build_nav_links
from .models import (
    PAGE_CATEGORIES,
    ContentPageConfig,
    FooterConfig,
    NavLinkConfig,
    PageConfig,
    SharedContentConfig,
    SiteConfig,
    SiteConfigError,
    SubSiteConfig,
    SubSiteHomepageConfig,
    ThemeConfig,
)


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
    default_category = defaults.get("category", PAGE_CATEGORIES[0])
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
        category=default_category,
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
        raw.get("about"),
        fallback_footer=homepage_config.footer if homepage_config else None,
    )

    shared_content = _build_shared_content_map(
        raw.get("shared_content"),
        config_dir=path.parent,
    )
    sites = _build_sites_map(
        raw.get("sites"),
        page_defaults=page_defaults,
        default_theme=default_theme,
        fallback_footer=homepage_config.footer if homepage_config else None,
    )

    return SiteConfig(
        pages=pages,
        default_page=default_page,
        docs_index_output=docs_index_output,
        theme=default_theme,
        homepage=homepage_config,
        about=about_config,
        sites=sites,
        shared_content=shared_content,
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
    category: str
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
    category = payload.get("category", defaults.category)
    if category not in PAGE_CATEGORIES:
        allowed = ", ".join(PAGE_CATEGORIES)
        msg = f"Page '{key}' has unknown category '{category}'. Allowed: {allowed}"
        raise SiteConfigError(msg)

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
        category=category,
    )


def _build_shared_content_map(
    raw: typ.Mapping[str, typ.Any] | None,
    *,
    config_dir: Path,
) -> dict[str, SharedContentConfig]:
    """Parse the top-level ``shared_content`` YAML block."""
    if not raw:
        return {}
    if not isinstance(raw, dict):
        msg = "shared_content must be a YAML mapping, got: " + type(raw).__name__
        raise SiteConfigError(msg)
    result: dict[str, SharedContentConfig] = {}
    for key, payload in raw.items():
        if not isinstance(payload, dict):
            msg = (
                f"Shared content entry '{key}' must be a mapping,"
                f" got: {type(payload).__name__}"
            )
            raise SiteConfigError(msg)
        label = payload.get("label")
        source = payload.get("source")
        output_slug = payload.get("output_slug")
        if not (label and source and output_slug):
            msg = (
                f"Shared content '{key}' requires 'label', 'source', and 'output_slug'."
            )
            raise SiteConfigError(msg)
        source_text = str(source)
        if "://" in source_text:
            resolved_source: str | Path = source_text
        else:
            source_path = Path(source_text)
            if source_path.is_absolute():
                resolved_source = source_path
            else:
                candidates = [config_dir / source_path]
                if source_text.startswith(f"{config_dir.name}/"):
                    candidates.append(config_dir.parent / source_path)
                resolved_source = next(
                    (candidate for candidate in candidates if candidate.exists()),
                    candidates[0],
                )
        eyebrow = payload.get("eyebrow")
        summary = payload.get("summary")
        result[key] = SharedContentConfig(
            key=key,
            label=str(label),
            source=str(resolved_source),
            output_slug=str(output_slug),
            eyebrow=str(eyebrow) if eyebrow else None,
            summary=str(summary) if summary else None,
            sections=bool(payload.get("sections", False)),
            toc=bool(payload.get("toc", False)),
            toc_exclude=_string_tuple(payload, "toc_exclude", key),
            divider_sections=_string_tuple(payload, "divider_sections", key),
        )
    return result


def _string_tuple(
    payload: typ.Mapping[str, typ.Any],
    field: str,
    entry_key: str,
) -> tuple[str, ...]:
    """Read an optional list of strings from a shared-content entry."""
    value = payload.get(field)
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        msg = f"Shared content '{entry_key}' field '{field}' must be a list of strings."
        raise SiteConfigError(msg)
    return tuple(value)


def _build_sites_map(
    raw: typ.Mapping[str, typ.Any] | None,
    *,
    page_defaults: _PageDefaults,
    default_theme: ThemeConfig,
    fallback_footer: FooterConfig | None,
) -> dict[str, SubSiteConfig]:
    """Parse the ``sites`` YAML block into sub-site configurations."""
    if not raw:
        return {}
    if not isinstance(raw, dict):
        msg = "sites must be a YAML mapping, got: " + type(raw).__name__
        raise SiteConfigError(msg)
    result: dict[str, SubSiteConfig] = {}
    for key, payload in raw.items():
        if not isinstance(payload, dict):
            msg = f"Site entry '{key}' must be a mapping, got: {type(payload).__name__}"
            raise SiteConfigError(msg)
        result[key] = _build_subsite_config(
            key=key,
            payload=payload,
            page_defaults=page_defaults,
            default_theme=default_theme,
            fallback_footer=fallback_footer,
        )
    return result


def _build_subsite_config(
    *,
    key: str,
    payload: typ.Mapping[str, typ.Any],
    page_defaults: _PageDefaults,
    default_theme: ThemeConfig,
    fallback_footer: FooterConfig | None,
) -> SubSiteConfig:
    """Build a single SubSiteConfig from its YAML mapping."""
    output_dir = Path(payload.get("output_dir", f"public/{key}"))
    templates_dir = Path(payload.get("templates_dir", f"templates/{key}"))
    stylesheet = payload.get("stylesheet", f"assets/{key}.css")
    base_path = payload.get("base_path", f"/{key}/")

    theme = _merge_theme(default_theme, payload.get("theme"))

    # Sub-site pages
    sub_page_defaults = dc.replace(
        page_defaults,
        theme=theme,
        output_dir=output_dir,
        filename_prefix=payload.get("filename_prefix", page_defaults.filename_prefix),
    )
    pages_raw = payload.get("pages") or {}
    pages: dict[str, PageConfig] = {}
    for page_key, page_payload in pages_raw.items():
        if isinstance(page_payload, dict):
            pages[page_key] = _build_page_config(
                key=page_key,
                payload=page_payload,
                defaults=sub_page_defaults,
            )

    # Docs index
    docs_index_raw = payload.get("docs_index_output")
    docs_index_output = Path(docs_index_raw) if docs_index_raw else None

    # Homepage
    homepage = _build_subsite_homepage(payload.get("homepage"), key, output_dir)

    # About page
    about_config = _build_about_config(
        payload.get("about"),
        fallback_footer=fallback_footer,
    )

    # Shared content references
    shared_refs_raw = payload.get("shared_content") or []
    if shared_refs_raw and not isinstance(shared_refs_raw, list):
        msg = (
            f"Site '{key}' shared_content must be a list,"
            f" got: {type(shared_refs_raw).__name__}"
        )
        raise SiteConfigError(msg)
    shared_content_refs = [str(ref) for ref in shared_refs_raw if ref]

    # Content pages
    content_pages = _build_content_pages(key, payload.get("content_pages"))

    # Navigation
    nav_links = _build_nav_links(payload.get("nav_links"))

    # Parent link
    parent_link = _build_parent_link(payload.get("parent_link"))

    # Static assets
    static_raw = payload.get("static_assets_dir")
    static_assets_dir = Path(static_raw) if static_raw else None

    return SubSiteConfig(
        key=key,
        output_dir=output_dir,
        templates_dir=templates_dir,
        stylesheet=str(stylesheet),
        base_path=str(base_path),
        theme=theme,
        pages=pages,
        homepage=homepage,
        about=about_config,
        docs_index_output=docs_index_output,
        shared_content_refs=shared_content_refs,
        nav_links=nav_links,
        parent_link=parent_link,
        static_assets_dir=static_assets_dir,
        content_pages=content_pages,
    )


def _build_subsite_homepage(
    raw: typ.Any,  # noqa: ANN401 -- YAML values are untyped
    key: str,
    output_dir: Path,
) -> SubSiteHomepageConfig | None:
    """Parse a sub-site homepage block into a typed config."""
    if not raw or not isinstance(raw, dict):
        return None
    hp_output = Path(raw.get("output", output_dir / "index.html"))
    hp_title = raw.get("title", f"{key} — Home")
    hp_context = {k: v for k, v in raw.items() if k not in {"output", "title"}}
    return SubSiteHomepageConfig(
        output=hp_output,
        title=str(hp_title),
        context=hp_context,
    )


def _build_parent_link(
    raw: typ.Any,  # noqa: ANN401 -- YAML values are untyped
) -> NavLinkConfig | None:
    """Parse an optional parent_link mapping into a NavLinkConfig."""
    if not isinstance(raw, dict):
        return None
    label = raw.get("label")
    href = raw.get("href")
    if not label or not href:
        return None
    return NavLinkConfig(
        label=str(label),
        href=str(href),
        variant=_optional_str(raw.get("variant")),
    )


def _build_content_pages(
    site_key: str,
    raw: list[typ.Any] | None,
) -> list[ContentPageConfig]:
    """Parse a ``content_pages`` YAML list into typed config objects."""
    if not raw:
        return []
    if not isinstance(raw, list):
        msg = (
            f"Site '{site_key}' content_pages must be a list, got: {type(raw).__name__}"
        )
        raise SiteConfigError(msg)
    result: list[ContentPageConfig] = []
    for entry in raw:
        if not isinstance(entry, dict):
            msg = (
                f"Site '{site_key}' content_pages entry must be a mapping,"
                f" got: {type(entry).__name__}"
            )
            raise SiteConfigError(msg)
        key = entry.get("key")
        template = entry.get("template")
        if not key or not template:
            msg = (
                f"Site '{site_key}' content_pages entry requires 'key' and 'template'."
            )
            raise SiteConfigError(msg)
        label = entry.get("label") or str(key).replace("-", " ").title()
        output_slug = entry.get("output_slug") or str(key)
        result.append(
            ContentPageConfig(
                key=str(key),
                label=str(label),
                template=str(template),
                output_slug=str(output_slug),
            )
        )
    return result


__all__ = ["load_site_config"]
