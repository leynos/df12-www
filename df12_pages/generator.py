"""High-level orchestration for documentation page generation."""

from __future__ import annotations

import dataclasses as dc
import datetime as dt
import json
import os
import posixpath
import re
import typing as typ
from email.utils import parsedate_to_datetime
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

import requests
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from github3 import GitHub
from github3 import exceptions as gh_exc
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown import Markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor
from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

from ._constants import PAGE_META_TEMPLATE
from .config import PageConfig, SectionLayout
from .docs_index import ManifestDescriptionResolver
from .markdown_parser import Section, Subsection, parse_sections

CODE_BLOCK_PATTERN = re.compile(r"```([A-Za-z0-9_+#.-]+)?[^\n]*\n(.*?)```", re.DOTALL)
FENCED_INDENT_PATTERN = re.compile(r"^[ ]{1,3}([`~]{3,})", re.MULTILINE)
FENCE_LABEL_PATTERN = re.compile(r"^([`~]{3,})([A-Za-z0-9_+#.-]+)?(,[^\r\n]+)$", re.MULTILINE)
CODEHILITE_OPEN_TAG = re.compile(r'<div class="codehilite">')


class HtmlContentRenderer:
    """Render markdown and code snippets with consistent styling."""

    def __init__(
        self, pygments_style: str = "monokai", link_extension: Extension | None = None
    ) -> None:
        self.pygments_style = pygments_style
        self._formatter = HtmlFormatter(style=pygments_style, cssclass="codehilite")
        self._link_extension = link_extension

    @property
    def stylesheet(self) -> str:
        """Return the CSS used for highlighted code blocks."""
        return self._formatter.get_style_defs(".codehilite")

    def markdown(self, text: str) -> str:
        """Render markdown into HTML using the configured extensions.

        Parameters
        ----------
        text : str
            Raw markdown content to render. Empty or whitespace-only strings
            return an empty result.

        Returns
        -------
        str
            HTML string with code blocks annotated for the df12 codehilite
            styling.
        """
        normalized = self._normalize_fenced_blocks(text)
        if not normalized.strip():
            return ""
        extensions: list[Extension | str] = [
            "fenced_code",
            "codehilite",
            "tables",
            "sane_lists",
        ]
        if self._link_extension:
            extensions.append(self._link_extension)
        md = Markdown(
            extensions=extensions,
            extension_configs={
                "codehilite": {
                    "linenums": False,
                    "guess_lang": False,
                    "css_class": "codehilite",
                    "pygments_style": self.pygments_style,
                }
            },
        )
        html = md.convert(normalized)
        return self._annotate_codehilite(html, normalized)

    def code_block(self, code: str, language: str | None = None) -> str:
        """Highlight fenced code blocks with pygments."""
        lang = language or "text"
        try:
            lexer = get_lexer_by_name(lang)
        except ClassNotFound:
            lexer = get_lexer_by_name("text")
        html = highlight(code, lexer, self._formatter)
        return self._attach_language_attribute(html, lang)

    def _annotate_codehilite(self, html: str, source_markdown: str) -> str:
        """Attach language metadata to each highlighted block in converted markdown."""
        languages = [match.group(1) or "text" for match in CODE_BLOCK_PATTERN.finditer(source_markdown)]
        if not languages:
            return html
        lang_iter = iter(languages)

        def _repl(match: re.Match[str]) -> str:
            lang = next(lang_iter, "text")
            return f'<div class="codehilite" data-language="{escape(lang, quote=True)}">'

        return CODEHILITE_OPEN_TAG.sub(_repl, html, len(languages))

    @staticmethod
    def _attach_language_attribute(html: str, language: str) -> str:
        """Add a single language attribute to an already highlighted block."""
        safe_lang = escape(language or "text", quote=True)

        def _repl(match: re.Match[str]) -> str:
            return f'<div class="codehilite" data-language="{safe_lang}">' 

        return CODEHILITE_OPEN_TAG.sub(_repl, html, 1)

    @staticmethod
    def _normalize_fenced_blocks(text: str) -> str:
        without_indent = FENCED_INDENT_PATTERN.sub(r"\1", text)

        def _strip_labels(match: re.Match[str]) -> str:
            fence, language, _extras = match.groups()
            label = language or ""
            return f"{fence}{label}"

        return FENCE_LABEL_PATTERN.sub(_strip_labels, without_indent)


@dc.dataclass(slots=True)
class SectionModel:
    """Structured data passed to the doc section template."""

    title: str
    short_title: str
    slug: str
    order: int
    layout: str
    intro_html: str
    default_html: str
    numbered_steps: list[dict[str, str]]
    split_panel: dict[str, str]
    subsections: list[dict[str, str]]
    toc_items: list[dict[str, str]]


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
        self.templates_dir = templates_dir or Path(__file__).parent / "templates"
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
        if self._github_client is None:
            token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
            self._github_client = GitHub(token=token)
        return self._github_client

    def _fetch_doc_commit_date(self) -> dt.datetime | None:
        repo_slug = self.page.repo
        if not repo_slug:
            return None
        try:
            owner, name = repo_slug.split("/", 1)
        except ValueError:
            return None

        branch = self.page.branch or "main"
        doc_path = self.page.doc_path.lstrip("/")

        try:
            repository = self._github().repository(owner, name)
        except gh_exc.GitHubException:
            return None
        if repository is None:
            return None
        try:
            commits = repository.commits(path=doc_path, sha=branch)
        except gh_exc.GitHubException:
            return None

        latest_commit = next(iter(commits), None)
        if not latest_commit:
            return None
        return self._extract_commit_timestamp(latest_commit)

    def _extract_commit_timestamp(self, commit: typ.Any) -> dt.datetime | None:
        commit_payload = getattr(commit, "commit", None)
        if commit_payload is None and isinstance(commit, dict):
            commit_payload = commit.get("commit")
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
    def _normalize_commit_date(value: typ.Any) -> dt.datetime | None:
        if value is None:
            return None
        if isinstance(value, dt.datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=dt.UTC)
            return value.astimezone(dt.UTC)
        if isinstance(value, str):
            sanitized = value.strip()
            if not sanitized:
                return None
            sanitized = sanitized.replace("Z", "+00:00")
            try:
                parsed = dt.datetime.fromisoformat(sanitized)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=dt.UTC)
            return parsed.astimezone(dt.UTC)
        return None

    def _fetch_markdown(self) -> str:
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
                self.doc_updated_at = self._extract_timestamp(resp.headers.get("Last-Modified"))
            return resp.text
        finally:
            session.close()

    def _resolve_source_url(self, override: str | None) -> str:
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
        filename = PAGE_META_TEMPLATE.format(key=self.page.key)
        return self.page.output_dir / filename

    def _write_metadata(self, first_filename: str) -> None:
        metadata = {"first_file": first_filename}
        path = self._metadata_path()
        try:
            path.write_text(json.dumps(metadata), encoding="utf-8")
        except OSError:  # pragma: no cover - IO issues
            return

    def _build_nav_groups(
        self, section_models: list[SectionModel]
    ) -> list[dict[str, typ.Any]]:
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
        return self.page.layouts.get(slug, SectionLayout())

    def _build_section_model(
        self, section: Section, layout: SectionLayout
    ) -> SectionModel:
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
        site_name = self.page.theme.site_name
        suffix = self.page.page_title_suffix
        return f"{site_name} — {section.short_title} | {suffix}"

    def _build_subsection_blocks(self, section: Section) -> list[dict[str, str]]:
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
        base_title = self._slugify(title)
        if base_title:
            base = f"{section_slug}-{base_title}"
        else:
            base = f"{section_slug}-part-{index}"
        return self._unique_anchor(base, used)

    @staticmethod
    def _unique_anchor(base: str, used: set[str]) -> str:
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = f"{base}-{suffix}"
            suffix += 1
        used.add(candidate)
        return candidate

    @staticmethod
    def _slugify(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

    @staticmethod
    def _clean_nav_label(label: str) -> str:
        return label.strip().rstrip(":").strip()


def _build_release_url(repo: str, tag: str, path: str) -> str:
    normalized = path.lstrip("/")
    return f"https://raw.githubusercontent.com/{repo}/refs/tags/{tag}/{normalized}"


def _build_link_rewriter(page: PageConfig) -> Extension | None:
    """Create a markdown extension that rewrites relative links to GitHub raw URLs.

    Parameters
    ----------
    page : PageConfig
        Page configuration containing the repo slug, release/branch ref, and
        markdown path used to derive relative link bases.

    Returns
    -------
    Extension or None
        RelativeLinkExtension configured for the page context, or ``None`` when
        the page does not originate from a GitHub repository.
    """
    if not page.repo:
        return None
    ref = page.latest_release or page.branch
    base_dir = posixpath.dirname(page.doc_path)
    return RelativeLinkExtension(page.repo, ref, base_dir)


class RelativeLinkExtension(Extension):
    """Markdown extension that rewrites relative links to GitHub sources."""

    def __init__(self, repo: str, ref: str, base_dir: str) -> None:
        """Initialize the link rewriter.

        Parameters
        ----------
        repo : str
            Owner/repository slug (e.g., ``leynos/netsuke``).
        ref : str
            Git reference (tag or branch) the document was fetched from.
        base_dir : str
            Directory path inside the repo that contains the markdown source.
        """
        self.repo = repo
        self.ref = ref
        self.base_dir = base_dir

    def extendMarkdown(self, md: Markdown) -> None:  # type: ignore[override]
        """Register the relative-link treeprocessor on the provided Markdown instance."""
        processor = RelativeLinkTreeprocessor(md, self.repo, self.ref, self.base_dir)
        md.treeprocessors.register(processor, "df12_relative_links", 15)


class RelativeLinkTreeprocessor(Treeprocessor):
    """Treeprocessor that rewrites relative markdown links to point at GitHub raw blobs."""

    def __init__(self, md: Markdown, repo: str, ref: str, base_dir: str) -> None:
        """Store repo metadata for rewriting relative links.

        Parameters
        ----------
        md : Markdown
            The Markdown instance the processor extends.
        repo : str
            Repository slug used to form GitHub URLs.
        ref : str
            Branch or tag name serving as the content reference.
        base_dir : str
            Directory path within the repository that contains the Markdown file.
        """
        super().__init__(md)
        self.repo = repo
        self.ref = ref
        self.base_dir = base_dir

    def run(self, root: typ.Any) -> typ.Any:  # pragma: no cover - Markdown API
        for element in root.iter():
            if element.tag == "a":
                href = element.get("href")
                rewritten = self._rewrite(href)
                if rewritten:
                    element.set("href", rewritten)
        return root

    def _rewrite(self, target: str | None) -> str | None:
        """Rewrite a relative link target into a GitHub raw URL when applicable.

        Parameters
        ----------
        target : str or None
            Original link target from the markdown document.

        Returns
        -------
        str or None
            Absolute GitHub raw URL when the link is relative to the source
            document; ``None`` for external schemes, anchors, double-slash URLs,
            or other non-relative targets.
        """
        if not target:
            return None
        lower = target.lower()
        if lower.startswith(("http://", "https://", "mailto:", "tel:", "data:", "javascript:")):
            return None
        if target.startswith(("#", "//")):
            return None
        if "://" in target:
            return None

        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or (not parsed.path and parsed.fragment):
            return None
        if parsed.path.startswith("/"):
            return None

        joined = posixpath.normpath(posixpath.join(self.base_dir, parsed.path))
        while joined.startswith("../"):
            joined = joined[3:]
        if joined in (".", ""):
            return None

        url = f"https://github.com/{self.repo}/blob/{self.ref}/{joined}"
        if parsed.query:
            url = f"{url}?{parsed.query}"
        if parsed.fragment:
            url = f"{url}#{parsed.fragment}"
        return url
