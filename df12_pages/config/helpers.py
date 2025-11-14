"""Utility helpers shared by the df12 configuration loader."""

from __future__ import annotations

import datetime as dt
import typing as typ

from .models import SectionLayout, ThemeConfig

DEFAULT_DOC_PATH = "docs/users-guide.md"
LANGUAGE_MANIFESTS: dict[str, str] = {
    "rust": "Cargo.toml",
    "python": "pyproject.toml",
    "typescript": "package.json",
}


def _normalize_classes(value: str | list[object] | None) -> list[str]:
    """Normalize class definitions into a list of non-empty strings."""
    if isinstance(value, str):
        return [segment for segment in value.split() if segment]
    if isinstance(value, list):
        normalized: list[str] = []
        for segment in value:
            text = str(segment).strip()
            if text:
                normalized.append(text)
        return normalized
    return []


def _optional_str(value: object | None) -> str | None:
    """Return a stripped string value or None when empty."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_repo_url(repo: str, ref: str, path: str) -> str:
    """Build the raw GitHub URL for a file at the given ref and path."""
    normalized = path.lstrip("/")
    ref_segment = ref if ref.startswith("refs/") else f"refs/heads/{ref}"
    return f"https://raw.githubusercontent.com/{repo}/{ref_segment}/{normalized}"


def _default_manifest_path(language: str | None) -> str | None:
    """Return the default manifest path for the given language, if any."""
    if not language:
        return None
    return LANGUAGE_MANIFESTS.get(language.lower())


def _merge_theme(
    base: ThemeConfig, override: typ.Mapping[str, typ.Any] | None
) -> ThemeConfig:
    """Merge an override theme mapping into the base ThemeConfig."""
    if not override:
        return base
    return ThemeConfig(
        hero_eyebrow=override.get("hero_eyebrow", base.hero_eyebrow),
        hero_tagline=override.get("hero_tagline", base.hero_tagline),
        doc_label=override.get("doc_label", base.doc_label),
        site_name=override.get("site_name", base.site_name),
    )


def _build_theme_config(payload: typ.Mapping[str, typ.Any]) -> ThemeConfig:
    """Build a ThemeConfig instance from the provided mapping payload."""
    base = ThemeConfig()
    return ThemeConfig(
        hero_eyebrow=payload.get("hero_eyebrow", base.hero_eyebrow),
        hero_tagline=payload.get("hero_tagline", base.hero_tagline),
        doc_label=payload.get("doc_label", base.doc_label),
        site_name=payload.get("site_name", base.site_name),
    )


def _merge_layouts(
    shared_layouts: typ.Mapping[str, typ.Any],
    page_layouts: typ.Mapping[str, typ.Any] | None,
) -> dict[str, SectionLayout]:
    """Merge shared and page-specific layout mappings into section layouts."""
    result: dict[str, SectionLayout] = {}
    combined: dict[str, typ.Any] = dict(shared_layouts)
    if page_layouts:
        combined.update(page_layouts)
    for slug, payload in combined.items():
        if not isinstance(payload, dict):
            continue
        result[slug] = SectionLayout(
            device=payload.get("device", "default"),
            step_order=list(payload.get("step_order", []) or []),
            emphasized_code_block=payload.get("emphasized_code_block"),
        )
    return result


def _parse_timestamp(value: dt.datetime | str | None) -> dt.datetime | None:
    """Return a timezone-aware UTC datetime parsed from ``value``, or None."""
    match value:
        case dt.datetime():
            parsed = value
        case str() as text:
            sanitized = text.strip()
            if not sanitized:
                return None
            if sanitized.endswith("Z"):
                sanitized = sanitized[:-1] + "+00:00"
            try:
                parsed = dt.datetime.fromisoformat(sanitized)
            except ValueError:
                return None
        case _:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


__all__ = [
    "DEFAULT_DOC_PATH",
    "LANGUAGE_MANIFESTS",
    "_build_repo_url",
    "_build_theme_config",
    "_default_manifest_path",
    "_merge_layouts",
    "_merge_theme",
    "_normalize_classes",
    "_optional_str",
    "_parse_timestamp",
]
