"""High-level orchestration for documentation page generation.

This module coordinates fetching markdown from GitHub (optionally pinned to a
release), rendering it with shared templates, and writing themed HTML bundles.
It exposes :class:`PageContentGenerator`, which consumes a
:class:`~df12_pages.config.PageConfig`, renders each section with
``HtmlContentRenderer``, and persists both HTML and metadata that power
``public/docs-*.html`` and ``docs.html``.

Example
-------
>>> from pathlib import Path
>>> from df12_pages.config import load_site_config
>>> from df12_pages.generator import PageContentGenerator
>>> config = load_site_config(Path("config/pages.yaml"))  # doctest: +SKIP
>>> page = config.get_page("getting-started")  # doctest: +SKIP
>>> generator = PageContentGenerator(page)  # doctest: +SKIP
>>> generator.run()  # doctest: +SKIP
[PosixPath('public/docs-getting-started.html'), ...]
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import typing as typ
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from github3 import GitHub
from github3 import exceptions as gh_exc
from jinja2 import Environment, FileSystemLoader, select_autoescape
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from df12_pages._constants import PAGE_META_TEMPLATE
from df12_pages.config import PageConfig, SectionLayout
from df12_pages.docs_index import ManifestDescriptionResolver
from df12_pages.generator.link_rewriter import _build_link_rewriter
from df12_pages.generator.models import SectionModel
from df12_pages.generator.renderer import CODE_BLOCK_PATTERN, HtmlContentRenderer
from df12_pages.markdown_parser import Section, Subsection, parse_sections


class PageContentGenerator:
    """Fetch page markdown and emit themed HTML per section."""

    def __init__(
        self,
        page_config: PageConfig,
        *,
        templates_dir: Path | None = None,
        source_url: str | None = None,
        output_dir: Path | None = None,
    ) -> None:
        """Initialize the generator with configuration and template context.

        Parameters
        ----------
        page_config : PageConfig
            Page configuration describing repo details, theming, and layout.
        templates_dir : Path, optional
            Directory containing Jinja templates; defaults to the package templates.
        source_url : str, optional
            Override for the document source URL; falls back to the page config.
        output_dir : Path, optional
            Override for the HTML output directory; defaults to the page config output.
        """
        self.page = page_config
        self.output_dir_override = output_dir
        default_templates = Path(__file__).resolve().parents[1] / "templates"
        self.templates_dir = templates_dir or default_templates
        self.renderer = HtmlContentRenderer(
            page_config.pygments_style, link_extension=_build_link_rewriter(page_config)
        )
        self.description_resolver = ManifestDescriptionResolver()
        self.page_description = self._resolve_description()
        self.doc_version: str | None = None
        self.doc_version_display: str | None = None
        self._github_client: GitHub | None = None
        self.doc_updated_at: dt.datetime | None = self._resolve_doc_updated_at()
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.template = self.env.get_template("doc_page.jinja")
        self.source_url = self._resolve_source_url(source_url)

    def run(self) -> list[Path]:
        """Render every section into themed HTML files on disk.

        Returns
        -------
        list[Path]
            Paths to the generated HTML documents, ordered by section.

        Raises
        ------
        RuntimeError
            Raised when the source markdown contains no second-level sections to render.

        Notes
        -----
        Side effects include writing HTML files and metadata artifacts into the
        configured output directory.
        """
        markdown_source = self._fetch_markdown()
        sections = parse_sections(markdown_source)
        if not sections:
            msg = "No second-level sections were found in the upstream markdown."
            raise RuntimeError(msg)

        out_dir = self.output_dir_override or self.page.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        generated_at = dt.datetime.now(dt.UTC)
        doc_updated_at = self.doc_updated_at or generated_at
        section_bundle: list[tuple[Section, SectionModel, str]] = []
        for section in sections:
            layout = self._resolve_layout(section.slug)
            section_model = self._build_section_model(section, layout)
            html_title = self._format_page_title(section)
            section_bundle.append((section, section_model, html_title))

        nav_groups = self._build_nav_groups([bundle[1] for bundle in section_bundle])
        written: list[Path] = []
        for section, section_model, html_title in section_bundle:
            context = {
                "section": section_model,
                "nav_groups": nav_groups,
                "theme": self.page.theme,
                "generated_at": generated_at,
                "doc_updated_at": doc_updated_at,
                "doc_version": self.doc_version_display,
                "source_url": self.source_url,
                "source_label": self.page.source_label,
                "pygments_css": self.renderer.stylesheet,
                "page": self.page,
                "page_description": self.page_description,
                "html_title": html_title,
                "footer_note": self.page.footer_note,
            }
            html = self.template.render(**context)
            filename = f"{self.page.filename_prefix}{section.slug}.html"
            output_path = out_dir / filename
            output_path.write_text(html, encoding="utf-8")
            written.append(output_path)
        if written:
            self._write_metadata(written[0].name)
        return written

    def _resolve_doc_updated_at(self) -> dt.datetime | None:
        if self.page.latest_release_published_at:
            return self.page.latest_release_published_at
        return self._fetch_doc_commit_date()

    def _github(self) -> GitHub:
        """Return a cached github3.py client, lazily configured from env tokens."""
        if self._github_client is None:
            token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
            self._github_client = GitHub(token=token)
        return self._github_client

    def _fetch_doc_commit_date(self) -> dt.datetime | None:
        """Return the latest commit timestamp for the page repo or None on errors."""
        result: dt.datetime | None = None
        repo_slug = self.page.repo
        if repo_slug:
            try:
                owner, name = repo_slug.split("/", 1)
            except ValueError:
                owner = name = None

            if owner and name:
                branch = self.page.branch or "main"
                doc_path = self.page.doc_path.lstrip("/")
                try:
                    repository = self._github().repository(owner, name)
                except gh_exc.GitHubException:
                    repository = None

                if repository is not None:
                    try:
                        commits = repository.commits(path=doc_path, sha=branch)
                    except gh_exc.GitHubException:
                        commits = None

                    if commits is not None:
                        latest_commit = next(iter(commits), None)
                        if latest_commit:
                            result = self._extract_commit_timestamp(latest_commit)

        return result

    def _extract_commit_timestamp(self, commit: object) -> dt.datetime | None:
        """Extract a commit datetime from github3 objects or dict payloads.

        Parameters
        ----------
        commit : object
            Commit object or dictionary exposing ``commit.author``/``committer``
            with ``date`` attributes.

        Returns
        -------
        datetime | None
            The first normalized commit timestamp, or ``None`` when unavailable.
        """
        commit_payload = getattr(commit, "commit", None)
        if commit_payload is None and isinstance(commit, dict):
            commit_payload = typ.cast("dict[str, typ.Any]", commit).get("commit")
        if commit_payload is None:
            return None

        actors: list[typ.Any] = []
        for attr in ("author", "committer"):
            actor = getattr(commit_payload, attr, None)
            if actor is None and isinstance(commit_payload, dict):
                actor = commit_payload.get(attr)
            if actor is not None:
                actors.append(actor)

        for actor in actors:
            date_value = getattr(actor, "date", None)
            if date_value is None and isinstance(actor, dict):
                date_value = actor.get("date")
            normalized = self._normalize_commit_date(date_value)
            if normalized:
                return normalized
        return None

    @staticmethod
    def _normalize_commit_date(value: object) -> dt.datetime | None:
        """Normalize a commit timestamp value into a UTC datetime, if possible."""
        result: dt.datetime | None = None
        if value is None:
            result = None
        elif isinstance(value, dt.datetime):
            if value.tzinfo is None:
                result = value.replace(tzinfo=dt.UTC)
            else:
                result = value.astimezone(dt.UTC)
        elif isinstance(value, str):
            sanitized = value.strip()
            if sanitized:
                sanitized = sanitized.replace("Z", "+00:00")
                try:
                    parsed = dt.datetime.fromisoformat(sanitized)
                except ValueError:
                    parsed = None
                if parsed is not None:
                    if parsed.tzinfo is None:
                        result = parsed.replace(tzinfo=dt.UTC)
                    else:
                        result = parsed.astimezone(dt.UTC)
        return result

    def _fetch_markdown(self) -> str:
        """Download markdown from the resolved source URL, updating doc timestamps."""
        session = requests.Session()
        retry = Retry(
            total=5,
            read=5,
            connect=3,
            backoff_factor=0.5,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=("GET", "HEAD"),
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        try:
            resp = session.get(self.source_url, timeout=30)
            resp.raise_for_status()
            if not self.doc_updated_at:
                self.doc_updated_at = self._extract_timestamp(
                    resp.headers.get("Last-Modified")
                )
            return resp.text
        finally:
            session.close()

    def _resolve_source_url(self, override: str | None) -> str:
        """Return the effective markdown source URL, tracking release versions."""
        if override:
            return override
        if self.page.repo and self.page.latest_release:
            self.doc_version = self.page.latest_release
            self.doc_version_display = self._strip_version_prefix(self.doc_version)
            return _build_release_url(
                self.page.repo, self.page.latest_release, self.page.doc_path
            )
        return self.page.source_url

    def _extract_timestamp(self, header_value: str | None) -> dt.datetime:
        """Parse an HTTP Last-Modified header into a timezone-aware UTC datetime."""
        if header_value:
            try:
                parsed = parsedate_to_datetime(header_value)
            except (TypeError, ValueError):
                parsed = None
            if parsed is not None:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=dt.UTC)
                return parsed.astimezone(dt.UTC)
        return dt.datetime.now(dt.UTC)

    def _resolve_description(self) -> str:
        """Return the page description override or fetch it from the manifest."""
        if self.page.description_override:
            return self.page.description_override
        return self.description_resolver.resolve(self.page)

    @staticmethod
    def _strip_version_prefix(tag: str | None) -> str | None:
        if not tag:
            return None
        if tag.upper().startswith("V") and len(tag) > 1:
            return tag[1:]
        return tag

    def _metadata_path(self) -> Path:
        """Return the path to the metadata JSON file for this page."""
        filename = PAGE_META_TEMPLATE.format(key=self.page.key)
        return self.page.output_dir / filename

    def _write_metadata(self, first_filename: str) -> None:
        """Persist the metadata JSON that records the first generated filename."""
        metadata = {"first_file": first_filename}
        path = self._metadata_path()
        try:
            path.write_text(json.dumps(metadata), encoding="utf-8")
        except OSError:  # pragma: no cover - IO issues
            return

    def _build_nav_groups(
        self, section_models: list[SectionModel]
    ) -> list[dict[str, typ.Any]]:
        """Build sidebar navigation groups and entries for the rendered sections."""
        groups: list[dict[str, typ.Any]] = []
        for model in section_models:
            page_url = f"{self.page.filename_prefix}{model.slug}.html"
            group_label = self._clean_nav_label(model.short_title)
            entries: list[dict[str, typ.Any]] = [
                {
                    "label": group_label,
                    "href": page_url,
                    "section_slug": model.slug,
                    "is_primary": True,
                }
            ]
            if model.subsections:
                for block in model.subsections:
                    href = f"{page_url}#{block['anchor']}"
                    entries.append(
                        {
                            "label": self._clean_nav_label(block["title"]),
                            "href": href,
                            "section_slug": model.slug,
                            "is_primary": False,
                        }
                    )
            groups.append(
                {"label": group_label, "slug": model.slug, "entries": entries}
            )
        return groups

    def _resolve_layout(self, slug: str) -> SectionLayout:
        """Return the configured SectionLayout for ``slug`` or a default layout."""
        return self.page.layouts.get(slug, SectionLayout())

    def _build_section_model(
        self, section: Section, layout: SectionLayout
    ) -> SectionModel:
        """Construct a SectionModel with rendered HTML and layout metadata."""
        intro_html = self.renderer.markdown(section.intro_markdown)
        default_html = self.renderer.markdown(section.markdown)
        numbered_steps: list[dict[str, str]] = []
        split_panel = {"primary_html": "", "secondary_html": ""}
        subsections = self._build_subsection_blocks(section)
        toc_items = [
            {"label": block["title"], "anchor": block["anchor"]}
            for block in subsections
        ]
        resolved_layout = layout.device

        if layout.device == "numbered_steps":
            numbered_steps = self._prepare_numbered_steps(section, layout)
            if not numbered_steps:
                resolved_layout = "default"
            else:
                toc_items = [
                    {"label": step["title"], "anchor": step["anchor"]}
                    for step in numbered_steps
                ]
        elif layout.device == "split_panel":
            split_panel = self._prepare_split_panel(section, layout)
            if not split_panel.get("secondary_html"):
                resolved_layout = "default"

        return SectionModel(
            title=section.title,
            short_title=section.short_title,
            slug=section.slug,
            order=section.order,
            layout=resolved_layout,
            intro_html=intro_html,
            default_html=default_html,
            numbered_steps=numbered_steps,
            split_panel=split_panel,
            subsections=subsections,
            toc_items=toc_items,
        )

    def _prepare_numbered_steps(
        self, section: Section, layout: SectionLayout
    ) -> list[dict[str, str]]:
        """Return numbered step data for ``section`` based on the provided layout."""
        subsections = list(section.subsections)
        if not subsections:
            return []

        if layout.step_order:
            ordered: list[Subsection] = []
            lower_map = {sub.title.lower(): sub for sub in subsections}
            for desired in layout.step_order:
                match = lower_map.get(desired.lower())
                if match and match not in ordered:
                    ordered.append(match)
            for sub in subsections:
                if sub not in ordered:
                    ordered.append(sub)
            subsections = ordered

        steps: list[dict[str, str]] = []
        for idx, sub in enumerate(subsections, start=1):
            html = self.renderer.markdown(sub.markdown)
            steps.append(
                {
                    "title": sub.title,
                    "number": idx,
                    "html": html,
                    "anchor": f"{section.slug}-step-{idx}",
                }
            )
        return steps

    def _prepare_split_panel(
        self, section: Section, layout: SectionLayout
    ) -> dict[str, str]:
        """Render split-panel HTML blocks for the section based on layout hints."""
        matches = list(CODE_BLOCK_PATTERN.finditer(section.markdown))
        if not matches:
            return {
                "primary_html": self.renderer.markdown(section.markdown),
                "secondary_html": "",
            }

        index = layout.emphasized_code_block or 0
        if index >= len(matches):
            index = 0
        match = matches[index]
        lang = match.group(1) or "text"
        code = match.group(2).strip("\n")
        before = section.markdown[: match.start()]
        after = section.markdown[match.end() :]
        primary_md = (before + "\n\n" + after).strip()
        return {
            "primary_html": self.renderer.markdown(primary_md),
            "secondary_html": self.renderer.code_block(code, lang),
        }

    def _format_page_title(self, section: Section) -> str:
        """Compose the HTML title using site name, section, and configured suffix."""
        site_name = self.page.theme.site_name
        suffix = self.page.page_title_suffix
        return f"{site_name} — {section.short_title} | {suffix}"

    def _build_subsection_blocks(self, section: Section) -> list[dict[str, str]]:
        """Return rendered subsection blocks with unique anchors for ``section``."""
        if not section.subsections:
            return []

        blocks: list[dict[str, str]] = []
        used: set[str] = set()
        for idx, sub in enumerate(section.subsections, start=1):
            anchor = self._section_anchor(section.slug, sub.title, idx, used)
            html = self.renderer.markdown(sub.markdown)
            blocks.append({"title": sub.title, "anchor": anchor, "html": html})
        return blocks

    def _section_anchor(
        self, section_slug: str, title: str, index: int, used: set[str]
    ) -> str:
        """Return a unique anchor combining section slug, slugified title, and index."""
        base_title = self._slugify(title)
        if base_title:
            base = f"{section_slug}-{base_title}"
        else:
            base = f"{section_slug}-part-{index}"
        return self._unique_anchor(base, used)

    @staticmethod
    def _unique_anchor(base: str, used: set[str]) -> str:
        """Return a unique anchor, appending numeric suffixes and mutating ``used``."""
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}-{suffix}"
            suffix += 1
        used.add(candidate)
        return candidate

    @staticmethod
    def _slugify(value: str) -> str:
        """Convert a string into a lowercase hyphen-separated slug."""
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

    @staticmethod
    def _clean_nav_label(label: str) -> str:
        """Trim surrounding whitespace and trailing colons from nav labels."""
        return label.strip().rstrip(":").strip()


def _build_release_url(repo: str, tag: str, path: str) -> str:
    """Return the raw GitHub URL for the file at ``path`` within a tagged release."""
    normalized = path.lstrip("/")
    return f"https://raw.githubusercontent.com/{repo}/refs/tags/{tag}/{normalized}"
