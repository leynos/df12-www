"""High-level orchestration for documentation page generation.

This module coordinates fetching markdown from GitHub (optionally pinned to a
release), rendering it with shared templates, and writing themed HTML bundles.
It exposes :class:`PageContentGenerator`, which consumes a
:class:`~df12_pages.config.PageConfig`, renders each section with
``HtmlContentRenderer``, and persists both HTML and metadata that power
``public/docs-*.html`` and ``docs.html``.

The work either side of the generator has its own module.
:mod:`df12_pages.generator.document_fetch` resolves and fetches a document,
returning the URL, version and date that actually answered as values, and
:mod:`df12_pages.generator.commit_date` resolves the date a page displays. Both
sets of names are re-exported here, so a caller can keep importing them from
this module.

Fetching, preparation and rendering are separate steps. :func:`fetch_document`
resolves a :class:`DocumentSource` to a :class:`FetchedMarkdown`, returning the
URL and version that actually answered as values.
:meth:`PageContentGenerator.prepare_document` is the preparation command: it
registers the page's template graph in the environment and compiles the
document's Mermaid figures. :meth:`PageContentGenerator.render_document` is the
query that follows it, turning prepared markdown into html without reading the
filesystem, consulting the environment or starting a subprocess. Only
:meth:`PageContentGenerator.render` reaches the network and selects the build
timestamp, which keeps the rendering rule testable with a fixture and no HTTP.

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

import dataclasses as dc
import json
import logging
import re
import typing as typ
from pathlib import Path

from df12_pages._constants import PAGE_META_TEMPLATE
from df12_pages.config import PageConfig, SectionLayout
from df12_pages.docs_index import ManifestDescriptionResolver
from df12_pages.generator.commit_date import resolve_doc_updated_at
from df12_pages.generator.document_fetch import (
    FETCH_TIMEOUT_SECONDS,
    DocumentFetcher,
    DocumentSource,
    FetchedMarkdown,
    MarkdownResponse,
    fetch_document,
    fetch_markdown,
    resolve_document_source,
)
from df12_pages.generator.link_rewriter import _build_link_rewriter
from df12_pages.generator.models import NumberedStep, SectionModel
from df12_pages.generator.renderer import (
    HtmlContentRenderer,
    MermaidRenderer,
    PreparedMarkdown,
)
from df12_pages.generator.section_render import (
    prepare_numbered_steps,
    prepare_split_panel,
)
from df12_pages.markdown_parser import Section, parse_sections
from df12_pages.templating import build_timestamp, template_environment

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    import datetime as dt

    from github3 import GitHub
    from minijinja import Environment

_log = logging.getLogger(__name__)

#: Template that renders one documentation section, and its relative suffix.
DOCUMENT_TEMPLATE = "doc_page.jinja"
_TEMPLATE_SUFFIX = ".jinja"

#: Templates shipped with the package, resolved once when the module loads.
#: Resolving here keeps construction free of filesystem metadata lookups.
DEFAULT_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"


class DocumentTemplate(typ.Protocol):
    """The slice of a template environment a document render needs.

    Registering the template graph is preparation; rendering then needs only
    these two calls, so a recorded template can stand in for the environment.
    """

    def add_template(self, name: str, source: str) -> None:
        """Register ``source`` under ``name``."""
        ...

    def render_template(self, template_name: str, /, **context: object) -> str:
        """Render the registered template ``template_name`` with ``context``."""
        ...


@dc.dataclass(frozen=True)
class PreparedDocument:
    """A document prepared for rendering without further preparation work.

    ``sections`` is the parsed document whose markdown has already been
    prepared, and ``template`` renders it. Both are values, so rendering the
    document reads no file, consults no environment and starts no subprocess.
    """

    sections: list[Section]
    template: DocumentTemplate
    markdown: PreparedMarkdown


@dc.dataclass(frozen=True)
class WrittenDocument:
    """What publishing one rendered bundle produced."""

    html_paths: list[Path]
    metadata_path: Path
    metadata_written: bool
    metadata_error: OSError | None = None


@dc.dataclass
class RenderedDocument:
    """HTML sections and the metadata destination for one documentation bundle."""

    output_dir: Path
    metadata_path: Path
    sections: list[tuple[str, str]]

    def write(self) -> WrittenDocument:
        """Write sections in order, then publish the index pointer to the first.

        Metadata is best effort: the HTML is already published, so a failed
        pointer must not fail the bundle. The outcome is returned rather than
        logged here, so the caller records it where it has the context.

        Returns
        -------
        WrittenDocument
            The written HTML paths, the index pointer's destination, and
            whether that pointer could be written. A failure carries the
            ``OSError`` that stopped it.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for filename, html in self.sections:
            path = self.output_dir / filename
            path.write_text(html, encoding="utf-8")
            written.append(path)
        metadata_written = False
        metadata_error: OSError | None = None
        if written:
            metadata = {"first_file": written[0].name}
            try:
                self.metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            except OSError as error:
                metadata_error = error
            else:
                metadata_written = True
        return WrittenDocument(
            html_paths=written,
            metadata_path=self.metadata_path,
            metadata_written=metadata_written,
            metadata_error=metadata_error,
        )


def publish_document(document: RenderedDocument) -> list[Path]:
    """Publish one bundle, reporting a metadata failure without raising.

    Parameters
    ----------
    document : RenderedDocument
        The rendered bundle to write.

    Returns
    -------
    list[Path]
        Written HTML paths in section order.
    """
    written = document.write()
    if written.html_paths and not written.metadata_written:
        _log.warning(
            "could not write document metadata for %s",
            written.metadata_path,
            exc_info=written.metadata_error,
        )
    return written.html_paths


class PageContentGenerator:
    """Fetch page markdown and emit themed HTML per section."""

    def __init__(  # noqa: PLR0913 -- one seam per injected collaborator
        self,
        page_config: PageConfig,
        *,
        templates_dir: Path | None = None,
        source_url: str | None = None,
        output_dir: Path | None = None,
        github_token: str | None = None,
        github_client: GitHub | None = None,
        doc_updated_at: dt.datetime | None = None,
        fetcher: DocumentFetcher = fetch_document,
        mermaid: MermaidRenderer | None = None,
    ) -> None:
        """Initialize the generator with configuration and template context.

        Construction performs no I/O: no document is fetched, no template is
        read, no path is resolved, no commit date is looked up and no output
        directory is created.
        The network is reached only by :meth:`render`; template and Mermaid
        I/O happens in :meth:`prepare_document`.

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
        github_token : str, optional
            Token used for the commit-date lookup. The caller reads it at the
            command boundary so this module never consults the environment.
        github_client : github3.GitHub, optional
            Client for the commit-date lookup, injected by tests and by callers
            that already hold one.
        doc_updated_at : datetime, optional
            Date already resolved for the document. The configured release
            date takes precedence over it.
        fetcher : DocumentFetcher, optional
            Callable that turns a :class:`DocumentSource` into markdown. Tests
            inject one that fails if called, to prove a path never fetches.
        mermaid : MermaidRenderer, optional
            Renderer for the document's fenced diagrams. Tests inject one that
            fails if called, to prove a path compiles no diagram.
        """
        self.page = page_config
        self.output_dir_override = output_dir
        self.templates_dir = templates_dir or DEFAULT_TEMPLATES_DIR
        self.renderer = HtmlContentRenderer(
            page_config.pygments_style,
            link_extension=_build_link_rewriter(page_config),
            mermaid=mermaid,
        )
        self._description_resolver = ManifestDescriptionResolver()
        self.env: Environment = template_environment(
            self.templates_dir, escape_by_suffix=True
        )
        self.source = resolve_document_source(page_config, source_url)
        self.doc_updated_at = page_config.latest_release_published_at or doc_updated_at
        self._github_token = github_token
        self._github_client = github_client
        self._fetcher = fetcher

    def run(self) -> list[Path]:
        """Render every section into themed HTML files on disk.

        Returns
        -------
        list[Path]
            Paths to the generated HTML documents, ordered by section.

        Raises
        ------
        requests.RequestException
            If the upstream document cannot be fetched.
        RuntimeError
            Raised when the source markdown contains no second-level sections to render.

        Notes
        -----
        Side effects include writing HTML files and metadata artifacts into the
        configured output directory.
        """
        return publish_document(self.render())

    def render(self) -> RenderedDocument:
        """Fetch the page's markdown and render it into an unpublished bundle.

        This is the command that reaches the network and the clock: it fetches
        the document, selects the build timestamp and, when no release date is
        configured, asks GitHub for the latest commit date. It then hands the
        markdown to :meth:`prepare_document` and the prepared result to
        :meth:`render_document`.

        Returns
        -------
        RenderedDocument
            The HTML and destination paths ready for the writer.

        Raises
        ------
        requests.RequestException
            If the document cannot be fetched, or a candidate fails for a
            reason other than a missing release-pinned document.
        RuntimeError
            If the upstream document has no second-level sections.
        """
        updated_at = self.doc_updated_at or resolve_doc_updated_at(
            self.page, token=self._github_token, client=self._github_client
        )
        fetched = self._fetcher(self.source, updated_at=updated_at)
        prepared = self.prepare_document(fetched.text)
        return self.render_document(
            prepared,
            source_url=fetched.source_url,
            # A fetcher reports a release tag, so it is displayed the way the
            # configured release pin is.
            version_display=DocumentSource(
                fetched.source_url, version=fetched.version
            ).version_display,
            page_description=self._resolve_description(),
            updated_at=fetched.updated_at,
            generated_at=build_timestamp(),
        )

    def prepare_document(self, markdown: str) -> PreparedDocument:
        """Do the document's side-effecting work ahead of rendering.

        This is a command, not a query. It registers every template in
        :attr:`templates_dir` with the environment, so rendering never returns
        to the filesystem, and it compiles the document's Mermaid fences to
        figures. What it returns is therefore safe to render anywhere.

        Parameters
        ----------
        markdown : str
            The document body as fetched.

        Returns
        -------
        PreparedDocument
            The parsed sections, the prepared markdown backing them, and the
            template that renders a section.

        Raises
        ------
        OSError
            If a template file cannot be read.
        """
        self._register_templates()
        content = self.renderer.prepare_markdown(markdown)
        return PreparedDocument(
            sections=parse_sections(content.markdown),
            template=self.env,
            markdown=content,
        )

    def _register_templates(self) -> None:
        """Register every template file so rendering never reads the disk.

        MiniJinja exposes no way to load a template without rendering it, so
        the whole directory is registered ahead of the first render. Registering
        an include as well as the document template is what keeps a lazy import
        from reaching back to the filesystem mid-render.
        """
        for path in sorted(self.templates_dir.rglob(f"*{_TEMPLATE_SUFFIX}")):
            name = path.relative_to(self.templates_dir).as_posix()
            self.env.add_template(name, path.read_text(encoding="utf-8"))

    def render_document(  # noqa: PLR0913 -- provenance and timestamp are values
        self,
        prepared: PreparedDocument,
        *,
        source_url: str,
        version_display: str | None,
        page_description: str,
        updated_at: dt.datetime | None = None,
        generated_at: dt.datetime,
    ) -> RenderedDocument:
        """Render a prepared document into an unpublished bundle.

        The method performs no I/O: it builds the section models from the
        supplied sections and renders the template against the supplied
        provenance. A caller can therefore render a fixture, or re-render a
        cached document, without a network call, a filesystem read, an
        environment lookup or an output write.

        Parameters
        ----------
        prepared : PreparedDocument
            The document returned by :meth:`prepare_document`.
        source_url : str
            URL the document was fetched from, shown in the page chrome.
        version_display : str or None
            Release version without its leading ``v``, or ``None`` when the
            document is not pinned to a release.
        page_description : str
            Description used in the page's metadata tags.
        updated_at : datetime, optional
            Date shown as the document's "Updated" badge; ``generated_at`` is
            used when omitted.
        generated_at : datetime
            The build timestamp to stamp the page with. It is a parameter
            rather than a lookup, so the same prepared document renders
            identically on every call.

        Returns
        -------
        RenderedDocument
            The HTML and destination paths ready for the writer.

        Raises
        ------
        RuntimeError
            If the prepared document has no second-level sections.
        """
        sections = prepared.sections
        if not sections:
            msg = "No second-level sections were found in the upstream markdown."
            raise RuntimeError(msg)

        out_dir = self.output_dir_override or self.page.output_dir

        doc_updated_at = updated_at or generated_at
        section_bundle: list[tuple[Section, SectionModel, str]] = []
        for section in sections:
            layout = self._resolve_layout(section.slug)
            section_model = self._build_section_model(
                section, layout, prepared.markdown.figures
            )
            html_title = self._format_page_title(section)
            section_bundle.append((section, section_model, html_title))

        nav_groups = self._build_nav_groups([bundle[1] for bundle in section_bundle])
        rendered = []
        for section, section_model, html_title in section_bundle:
            context = {
                "section": section_model,
                "nav_groups": nav_groups,
                "theme": self.page.theme,
                "generated_at": generated_at,
                "doc_updated_at": doc_updated_at,
                "doc_version": version_display,
                "source_url": source_url,
                "source_label": self.page.source_label,
                "pygments_css": self.renderer.stylesheet,
                "page": self.page,
                "page_description": page_description,
                "html_title": html_title,
                "footer_note": self.page.footer_note,
            }
            html = prepared.template.render_template(DOCUMENT_TEMPLATE, **context)
            filename = f"{self.page.filename_prefix}{section.slug}.html"
            rendered.append((filename, html))
        return RenderedDocument(out_dir, self._metadata_path(), rendered)

    def _resolve_description(self) -> str:
        """Return the page description override or fetch it from the manifest."""
        if self.page.description_override:
            return self.page.description_override
        return self._description_resolver.resolve(self.page)

    def _metadata_path(self) -> Path:
        """Return the path to the metadata JSON file for this page."""
        filename = PAGE_META_TEMPLATE.format(key=self.page.key)
        return self.page.output_dir / filename

    def _build_nav_groups(
        self, section_models: list[SectionModel]
    ) -> list[dict[str, typ.Any]]:
        """Build sidebar navigation groups and entries for the rendered sections."""
        groups: list[dict[str, typ.Any]] = []
        for model in section_models:
            page_url = f"/{self.page.filename_prefix}{model.slug}.html"
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
        self,
        section: Section,
        layout: SectionLayout,
        figures: cabc.Mapping[str, str],
    ) -> SectionModel:
        """Construct a SectionModel with rendered HTML and layout metadata."""
        intro_html = self.renderer.markdown(section.intro_markdown, figures=figures)
        default_html = self.renderer.markdown(section.markdown, figures=figures)
        numbered_steps: list[NumberedStep] = []
        split_panel = {"primary_html": "", "secondary_html": ""}
        subsections = self._build_subsection_blocks(section, figures)
        toc_items = [
            {"label": block["title"], "anchor": block["anchor"]}
            for block in subsections
        ]
        resolved_layout = layout.device

        if layout.device == "numbered_steps":
            numbered_steps = prepare_numbered_steps(
                self.renderer,
                section,
                layout,
                figures=figures,
                subsection_anchors=[block["anchor"] for block in subsections],
            )
            if not numbered_steps:
                resolved_layout = "default"
            else:
                toc_items = [
                    {"label": step["title"], "anchor": step["anchor"]}
                    for step in numbered_steps
                ]
        elif layout.device == "split_panel":
            split_panel = prepare_split_panel(self.renderer, section, layout, figures)
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

    def _format_page_title(self, section: Section) -> str:
        """Compose the HTML title using site name, section, and configured suffix."""
        site_name = self.page.theme.site_name
        suffix = self.page.page_title_suffix
        return f"{site_name} — {section.short_title} | {suffix}"

    def _build_subsection_blocks(
        self, section: Section, figures: cabc.Mapping[str, str]
    ) -> list[dict[str, str]]:
        """Return rendered subsection blocks with unique anchors for ``section``."""
        if not section.subsections:
            return []

        blocks: list[dict[str, str]] = []
        used: set[str] = set()
        for idx, sub in enumerate(section.subsections, start=1):
            anchor = self._section_anchor(section.slug, sub.title, idx, used)
            html = self.renderer.markdown(sub.markdown, figures=figures)
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


__all__ = [
    "DEFAULT_TEMPLATES_DIR",
    "DOCUMENT_TEMPLATE",
    "FETCH_TIMEOUT_SECONDS",
    "DocumentFetcher",
    "DocumentSource",
    "DocumentTemplate",
    "FetchedMarkdown",
    "MarkdownResponse",
    "PageContentGenerator",
    "PreparedDocument",
    "RenderedDocument",
    "WrittenDocument",
    "fetch_document",
    "fetch_markdown",
    "publish_document",
    "resolve_doc_updated_at",
    "resolve_document_source",
]
