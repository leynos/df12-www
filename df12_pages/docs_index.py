"""Build and render the df12 documentation index landing page.

This module takes a fully resolved :class:`~df12_pages.config.SiteConfig` and
produces ``public/docs.html`` (or the configured output path) listing every
generated documentation bundle. It stitches together metadata, release
information, manifest descriptions, and package links so readers can discover
docs quickly.

Typical usage pairs the loader with a site config:

>>> from pathlib import Path
>>> from df12_pages.config import load_site_config
>>> from df12_pages.docs_index import DocsIndexBuilder
>>> site = load_site_config(Path("config/pages.yaml"))  # doctest: +SKIP
>>> builder = DocsIndexBuilder(site)  # doctest: +SKIP
>>> output_path = builder.run()  # doctest: +SKIP
>>> print(output_path)  # doctest: +SKIP
public/docs.html

The builder reads Jinja templates from ``df12_pages/templates`` by default,
fetches manifest descriptions as needed, and writes UTF-8 encoded HTML. Side
effects include HTTP fetches (with caching) for manifest files and disk writes
to the docs output directory.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import tomllib
import typing as typ
from pathlib import Path

import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown import markdown

from ._constants import PAGE_META_TEMPLATE

if typ.TYPE_CHECKING:  # pragma: no cover - import for type hints only
    from .config import PageConfig, SiteConfig


class DocsIndexBuilder:
    """Render a landing page enumerating generated documentation bundles."""

    def __init__(
        self, site_config: SiteConfig, *, templates_dir: Path | None = None
    ) -> None:
        """Initialize the docs index builder.

        Parameters
        ----------
        site_config : SiteConfig
            Parsed site configuration containing all page definitions and
            defaults (produced by :func:`df12_pages.config.load_site_config`).
        templates_dir : Path, optional
            Directory containing the Jinja templates. Defaults to the
            ``df12_pages/templates`` directory when ``None``.
        """
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
        self._markdown_extensions = ["sane_lists", "tables", "fenced_code"]

    def run(self) -> Path:
        """Render the docs index HTML file to the configured output path."""
        entries = self._gather_entries()
        generated_at = dt.datetime.now(dt.UTC)
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
        """Collect and return documentation entry dictionaries for the site."""
        entries: list[dict[str, str]] = []
        docs_root = self.site_config.docs_index_output.parent
        for page in self.site_config.pages.values():
            link = _discover_entry_href(page, docs_root)
            if not link:
                continue
            description = (
                page.description_override or self.description_resolver.resolve(page)
            )
            entries.append(
                {
                    "label": page.label,
                    "description": description,
                    "description_html": self._render_description(description),
                    "href": link,
                    "repo": page.repo or "",
                    "repo_url": _build_repo_url(page.repo),
                    "latest_release": page.latest_release,
                    "release_url": _build_release_link(page.repo, page.latest_release),
                    "package_url": _build_package_url(page),
                    "package_label": _package_label(page.language),
                }
            )
        return entries

    def _render_description(self, text: str) -> str:
        normalized = (text or "").strip()
        if not normalized:
            return ""
        return markdown(
            normalized,
            extensions=self._markdown_extensions,
            output_format="html5",
        )


def _discover_entry_href(page: PageConfig, relative_to: Path) -> str | None:
    """Resolve the href used by docs index cards.

    Parameters
    ----------
    page : PageConfig
        Fully resolved page metadata whose generated HTML files live under
        ``page.output_dir``.
    relative_to : Path
        Directory that serves as the reference for relative hyperlinks in the
        docs index (typically ``public``).

    Returns
    -------
    str | None
        Relative POSIX path to the best candidate HTML file, or ``None`` when no
        generated documents exist for the page.

    Notes
    -----
    The function favors explicit metadata recorded in
    ``docs-<key>.meta.json`` (via ``first_file``) and only falls back to
    globbing the ``page.output_dir`` for ``{filename_prefix}*.html`` when that
    metadata is absent or stale.
    """
    meta_candidate = _read_page_metadata(page)
    if meta_candidate:
        rel = _relativize(meta_candidate, relative_to)
        if rel:
            return rel

    pattern = f"{page.filename_prefix}*.html"
    files = sorted(page.output_dir.glob(pattern), key=_doc_file_score)
    if not files:
        return None
    target = files[0]
    rel_path = Path(os.path.relpath(target, start=relative_to))
    return rel_path.as_posix()


def _doc_file_score(path: Path) -> tuple[int, str]:
    """Return a sorting key (priority, name) for documentation files."""
    name = path.name.lower()
    if "introduction" in name:
        return (0, name)
    if "getting-started" in name:
        return (1, name)
    return (2, name)


def _read_page_metadata(page: PageConfig) -> Path | None:
    """Return the first rendered file path recorded in page metadata, if present."""
    meta_path = page.output_dir / PAGE_META_TEMPLATE.format(key=page.key)
    if not meta_path.exists():
        return None
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):  # pragma: no cover - IO guard
        return None
    candidate = payload.get("first_file")
    if not candidate:
        return None
    full_path = page.output_dir / candidate
    if not full_path.exists():
        return None
    return full_path


def _relativize(target: Path, relative_to: Path) -> str | None:
    """Return the POSIX-relative path from ``relative_to`` to ``target`` or None."""
    try:
        # Use os.path.relpath instead of Path.relative_to for cross-drive and
        # non-parent relationships, where Path.relative_to would raise ValueError.
        rel_path = Path(os.path.relpath(target, start=relative_to))
    except ValueError:  # pragma: no cover - different drives
        return None
    return rel_path.as_posix()


def _build_repo_url(repo: str | None) -> str | None:
    """Return the GitHub repository URL built from ``repo`` (owner/repo)."""
    if not repo:
        return None
    return f"https://github.com/{repo}"


def _build_release_link(repo: str | None, tag: str | None) -> str | None:
    """Return the GitHub release URL for ``repo`` and ``tag``, or None if missing."""
    if not repo or not tag:
        return None
    return f"https://github.com/{repo}/releases/tag/{tag}"


def _package_slug(page: PageConfig) -> str | None:
    """Return the package/repo slug derived from ``page.repo`` or fallback key."""
    if page.repo:
        return page.repo.split("/", 1)[-1]
    return page.key


def _build_package_url(page: PageConfig) -> str | None:
    """Return the package registry URL for the page language and slug."""
    if not page.latest_release:
        return None
    slug = _package_slug(page)
    if not slug or not page.language:
        return None
    templates = {
        "rust": "https://crates.io/crates/{slug}",
        "python": "https://pypi.org/project/{slug}/",
        "typescript": "https://www.npmjs.com/package/{slug}",
        "javascript": "https://www.npmjs.com/package/{slug}",
    }
    template = templates.get(page.language.lower())
    if not template:
        return None
    return template.format(slug=slug)


def _package_label(language: str | None) -> str | None:
    """Return the package registry label (crates.io/PyPI/npm) for the language."""
    if not language:
        return None
    mapping = {
        "rust": "crates.io",
        "python": "PyPI",
        "typescript": "npm",
        "javascript": "npm",
    }
    return mapping.get(language.lower())


class ManifestDescriptionResolver:
    """Resolve project descriptions from manifests with caching."""

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    def resolve(self, page: PageConfig) -> str:
        """Resolve or fetch a manifest description for the provided page.

        Parameters
        ----------
        page : PageConfig
            Page metadata containing label, manifest URL, and language hints
            used to locate the appropriate manifest file.

        Returns
        -------
        str
            Either the manifest-provided description or a fallback string of
            the form ``"Reference docs for <label>."`` when fetching/parsing
            fails.

        Notes
        -----
        Results are cached per manifest URL to avoid repeated HTTP requests.
        Network or parsing errors are swallowed and replaced with the fallback
        description to keep docs generation resilient.
        """
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
        except (ValueError, TypeError):  # pragma: no cover - parse failure fallback
            description = None
        if not description:
            description = f"Reference docs for {page.label}."
        self._cache[url] = description
        return description


def _extract_description(text: str, language: str | None, url: str) -> str | None:
    """Return a manifest-derived description string based on language hints."""
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
