"""Site-level configuration loader for df12 page generation."""

from __future__ import annotations

import dataclasses as dc
from pathlib import Path
import typing as typ

from ruamel.yaml import YAML


@dc.dataclass(slots=True)
class SectionLayout:
    """Describes how a section should be presented."""

    device: str = "default"
    step_order: list[str] = dc.field(default_factory=list)
    emphasized_code_block: int | None = None


@dc.dataclass(slots=True)
class ThemeConfig:
    hero_eyebrow: str = "df12"
    hero_tagline: str = "Documentation"
    doc_label: str = "Docs"
    site_name: str = "df12 Productions"


DEFAULT_DOC_PATH = "docs/users-guide.md"
LANGUAGE_MANIFESTS: dict[str, str] = {
    "rust": "Cargo.toml",
    "python": "pyproject.toml",
    "typescript": "package.json",
}


@dc.dataclass(slots=True)
class PageConfig:
    key: str
    label: str
    source_url: str
    source_label: str
    page_title_suffix: str
    filename_prefix: str
    output_dir: Path
    pygments_style: str
    footer_note: str
    theme: ThemeConfig
    layouts: dict[str, SectionLayout]
    repo: str | None
    branch: str
    language: str | None
    manifest_url: str | None
    description_override: str | None


@dc.dataclass(slots=True)
class SiteConfig:
    pages: dict[str, PageConfig]
    default_page: str | None = None
    docs_index_output: Path = Path("public/docs.html")
    theme: ThemeConfig | None = None

    def get_page(self, page_id: str | None) -> PageConfig:
        """Return the requested page or fall back to the configured default."""

        if page_id is None:
            return self._get_default_page()
        try:
            return self.pages[page_id]
        except KeyError as exc:  # pragma: no cover - defensive guard
            available = ", ".join(sorted(self.pages))
            msg = f"Unknown page '{page_id}'. Known pages: {available}"
            raise KeyError(msg) from exc

    def _get_default_page(self) -> PageConfig:
        if self.default_page and self.default_page in self.pages:
            return self.pages[self.default_page]
        if not self.pages:  # pragma: no cover - configuration error
            raise ValueError("No pages configured in layout file.")
        first_key = next(iter(self.pages))
        return self.pages[first_key]


def load_site_config(path: Path) -> SiteConfig:
    """Load the YAML configuration describing page/site layout choices."""

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
        raise ValueError("No pages defined in layout configuration.")

    pages: dict[str, PageConfig] = {}
    for key, payload in pages_raw.items():
        if not isinstance(payload, dict):
            continue
        repo = payload.get("repo", default_repo)
        branch = payload.get("branch", default_branch)
        language = payload.get("language", default_language)
        doc_path = payload.get("doc_path", default_doc_path)
        source_url = payload.get("source_url")
        if not source_url and repo:
            source_url = _build_repo_url(repo, branch, doc_path)
        if not source_url:
            raise ValueError(f"Page '{key}' is missing 'source_url' or 'repo'.")

        label = payload.get("label") or key.replace("-", " ").title()
        source_label = payload.get("source_label", default_source_label)
        title_suffix = payload.get("page_title_suffix", default_page_title_suffix)
        filename_prefix = payload.get("filename_prefix", default_filename_prefix)
        output_dir = Path(payload.get("output_dir", default_output_dir))
        pygments_style = payload.get("pygments_style", default_pygments_style)
        footer_note = payload.get("footer_note", default_footer_note)
        theme = _merge_theme(default_theme, payload.get("theme"))

        layouts = _merge_layouts(shared_layouts, payload.get("layouts"))

        manifest_url = payload.get("manifest_url")
        if not manifest_url and repo:
            manifest_path = payload.get("manifest_path") or _default_manifest_path(language)
            if manifest_path:
                manifest_url = _build_repo_url(repo, branch, manifest_path)

        description_override = payload.get("description")

        pages[key] = PageConfig(
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
        )

    return SiteConfig(pages=pages, default_page=default_page, docs_index_output=docs_index_output, theme=default_theme)


def _build_repo_url(repo: str, branch: str, path: str) -> str:
    normalized = path.lstrip("/")
    return f"https://raw.githubusercontent.com/{repo}/refs/heads/{branch}/{normalized}"


def _default_manifest_path(language: str | None) -> str | None:
    if not language:
        return None
    return LANGUAGE_MANIFESTS.get(language.lower())


def _merge_theme(base: ThemeConfig, override: typ.Mapping[str, typ.Any] | None) -> ThemeConfig:
    if not override:
        return base
    return ThemeConfig(
        hero_eyebrow=override.get("hero_eyebrow", base.hero_eyebrow),
        hero_tagline=override.get("hero_tagline", base.hero_tagline),
        doc_label=override.get("doc_label", base.doc_label),
        site_name=override.get("site_name", base.site_name),
    )


def _build_theme_config(payload: typ.Mapping[str, typ.Any]) -> ThemeConfig:
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
