"""Docs index builder for df12 documentation bundles."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
import typing as typ

import requests
import tomllib
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import PageConfig, SiteConfig


class DocsIndexBuilder:
    """Render a landing page enumerating generated documentation bundles."""

    def __init__(self, site_config: SiteConfig, *, templates_dir: Path | None = None) -> None:
        self.site_config = site_config
        self.templates_dir = templates_dir or Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.template = self.env.get_template("docs_index.jinja")
        self.description_resolver = ManifestDescriptionResolver()

    def run(self) -> Path:
        entries = self._gather_entries()
        generated_at = datetime.now(timezone.utc)
        output_path = self.site_config.docs_index_output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        context = {
            "theme": self.site_config.theme,
            "entries": entries,
            "generated_at": generated_at,
        }
        html = self.template.render(**context)
        output_path.write_text(html, encoding="utf-8")
        return output_path

    def _gather_entries(self) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        docs_root = self.site_config.docs_index_output.parent
        for page in self.site_config.pages.values():
            link = _discover_entry_href(page, docs_root)
            if not link:
                continue
            description = page.description_override or self.description_resolver.resolve(page)
            entries.append(
                {
                    "label": page.label,
                    "description": description,
                    "href": link,
                    "repo": page.repo or "",
                }
            )
        return entries


def _discover_entry_href(page: PageConfig, relative_to: Path) -> str | None:
    pattern = f"{page.filename_prefix}*.html"
    files = sorted(page.output_dir.glob(pattern), key=_doc_file_score)
    if not files:
        return None
    target = files[0]
    rel_path = Path(os.path.relpath(target, start=relative_to))
    return rel_path.as_posix()


def _doc_file_score(path: Path) -> tuple[int, str]:
    name = path.name.lower()
    if "introduction" in name:
        return (0, name)
    if "getting-started" in name:
        return (1, name)
    return (2, name)


class ManifestDescriptionResolver:
    """Resolve project descriptions from manifests with caching."""

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    def resolve(self, page: PageConfig) -> str:
        url = page.manifest_url
        if not url:
            return f"Reference docs for {page.label}."
        if url in self._cache:
            return self._cache[url]
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException:
            return f"Reference docs for {page.label}."
        try:
            description = _extract_description(resp.text, page.language, url)
        except Exception:  # pragma: no cover - manifest parse failure fallback
            description = None
        if not description:
            description = f"Reference docs for {page.label}."
        self._cache[url] = description
        return description


def _extract_description(text: str, language: str | None, url: str) -> str | None:
    lang = (language or "").lower()
    if lang in {"rust", "python"} or url.endswith(".toml"):
        data = tomllib.loads(text)
        if lang == "python":
            return (data.get("project") or {}).get("description")
        package = data.get("package") or {}
        desc = package.get("description")
        if desc:
            return desc
        workspace = data.get("workspace") or {}
        return workspace.get("description")
    if lang == "typescript" or url.endswith(".json"):
        data = json.loads(text)
        return data.get("description")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data.get("description")
