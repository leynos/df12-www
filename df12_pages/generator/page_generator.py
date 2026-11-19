"""High-level orchestration for documentation page generation.

This module coordinates fetching markdown from GitHub (optionally pinned to a
release), rendering it with shared templates, and writing themed HTML bundles.
It exposes :class:`PageContentGenerator`, which consumes a
:class:`~df12_pages.config.PageConfig`, renders each section with
``HtmlContentRenderer``, and persists both HTML and metadata that power
``public/docs-*.html`` and ``docs.html``.

Fetching and rendering are separate steps. :func:`fetch_document` resolves a
:class:`DocumentSource` to a :class:`FetchedMarkdown`, returning the URL and
version that actually answered as values; :meth:`PageContentGenerator.render_document`
turns markdown it is given into html and performs no I/O. Only
:meth:`PageContentGenerator.render` reaches the network, which keeps the
rendering rule testable with a fixture and no HTTP.

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
import datetime as dt
import json
import logging
import re
import typing as typ
from pathlib import Path

import requests
from github3 import GitHub
from github3 import exceptions as gh_exc
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from df12_pages._constants import PAGE_META_TEMPLATE
from df12_pages.config import PageConfig, SectionLayout
from df12_pages.docs_index import ManifestDescriptionResolver
from df12_pages.generator.link_rewriter import _build_link_rewriter
from df12_pages.generator.models import NumberedStep, SectionModel
from df12_pages.generator.renderer import CODE_BLOCK_PATTERN, HtmlContentRenderer
from df12_pages.markdown_parser import Section, Subsection, parse_sections
from df12_pages.templating import build_timestamp, template_environment

_log = logging.getLogger(__name__)

#: Seconds to wait for one markdown response before the fetch fails.
FETCH_TIMEOUT_SECONDS = 30


@dc.dataclass(frozen=True)
class DocumentSource:
    """The URL a documentation page's markdown is fetched from."""

    source_url: str
    #: Raw URL of the same document inside the tagged release, when pinned.
    release_url: str | None = None
    #: Release tag the document is pinned to, without any rewriting.
    version: str | None = None

    @property
    def version_display(self) -> str | None:
        """Return the release version without its leading ``v``, if any."""
        return _strip_version_prefix(self.version)

    def attempts(self) -> list[tuple[str, str | None]]:
        """Return the URLs to try in order, each paired with its version pin.

        The pinned release is tried first. The branch source follows it with
        no version, so a guide added after the release was cut can still be
        rendered without claiming to belong to that release.
        """
        if self.release_url and self.release_url != self.source_url:
            return [(self.release_url, self.version), (self.source_url, None)]
        return [(self.source_url, self.version)]


@dc.dataclass(frozen=True)
class FetchedMarkdown:
    """A markdown body and the provenance that actually answered for it."""

    text: str
    source_url: str
    version: str | None = None
    updated_at: dt.datetime | None = None


class DocumentFetcher(typ.Protocol):
    """A callable that fetches one document source."""

    def __call__(
        self, source: DocumentSource, *, updated_at: dt.datetime | None = None
    ) -> FetchedMarkdown:
        """Fetch ``source``, returning its text and provenance."""
        ...


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


def _strip_version_prefix(tag: str | None) -> str | None:
    """Strip a leading ``v`` or ``V`` if more follows; ``None`` if empty."""
    if not tag:
        return None
    if tag.upper().startswith("V") and len(tag) > 1:
        return tag[1:]
    return tag


def resolve_document_source(
    page: PageConfig, override: str | None = None
) -> DocumentSource:
    """Return the URLs a page's markdown may be fetched from.

    Parameters
    ----------
    page : PageConfig
        Page configuration carrying the repository, release and source URL.
    override : str, optional
        Explicit source URL that replaces any release pin.

    Returns
    -------
    DocumentSource
        The pinned release URL when the page names a release, otherwise the
        configured branch source URL.
    """
    if override:
        return DocumentSource(override)
    if page.repo and page.latest_release:
        return DocumentSource(
            source_url=page.source_url,
            release_url=_build_release_url(
                page.repo, page.latest_release, page.doc_path
            ),
            version=page.latest_release,
        )
    return DocumentSource(page.source_url)


def _retrying_session() -> requests.Session:
    """Return a session that retries transient failures with backoff."""
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
    return session


def fetch_markdown(
    url: str, *, session: requests.Session, timeout: int = FETCH_TIMEOUT_SECONDS
) -> str:
    """Download one URL and return its body as text.

    Parameters
    ----------
    url : str
        Absolute URL of the markdown document.
    session : requests.Session
        Session carrying the retry policy; the caller owns its lifetime.
    timeout : int, optional
        Seconds to wait for the response.

    Returns
    -------
    str
        The response body.

    Raises
    ------
    requests.RequestException
        If the request fails at the transport level, or if the response is an
        HTTP error. Failures are raised rather than replaced with empty text,
        so a missing document cannot be published as a blank page.
    """
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def _http_status(error: requests.HTTPError) -> int | None:
    """Return the status of the response that raised ``error``, if attached."""
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None)


def fetch_document(
    source: DocumentSource,
    *,
    updated_at: dt.datetime | None = None,
    session: requests.Session | None = None,
) -> FetchedMarkdown:
    """Fetch the first URL of ``source`` that answers.

    A release-pinned URL that returns HTTP 404 falls back to the branch source
    URL. The version pin is dropped with it, and so is ``updated_at``: a guide
    added after the release was cut should still render, but neither it nor
    its date may claim to belong to that release.

    Parameters
    ----------
    source : DocumentSource
        Candidate URLs, pinned release first.
    updated_at : datetime, optional
        Date already known for the document, carried into the result.
    session : requests.Session, optional
        Session to fetch through; a retrying session is created and closed
        when omitted.

    Returns
    -------
    FetchedMarkdown
        The body plus the URL and version that actually answered.

    Raises
    ------
    requests.RequestException
        If a candidate fails for a reason other than a missing pinned release,
        or if every candidate fails. The error from the failing request is
        allowed to escape rather than being replaced by an empty document.
    """
    owned = session is None
    active = session or _retrying_session()
    try:
        attempts = source.attempts()
        for index, (url, version) in enumerate(attempts):
            try:
                text = fetch_markdown(url, session=active)
            except requests.HTTPError as error:
                last_attempt = index == len(attempts) - 1
                if last_attempt or _http_status(error) != requests.codes.not_found:
                    raise
                continue
            return FetchedMarkdown(
                text=text,
                source_url=url,
                version=version,
                updated_at=updated_at if index == 0 else None,
            )
    finally:
        if owned:
            active.close()
    msg = "a document source must offer at least one URL"
    raise AssertionError(msg)


def resolve_doc_updated_at(
    page: PageConfig,
    *,
    token: str | None = None,
    client: GitHub | None = None,
) -> dt.datetime | None:
    """Return the date to show for ``page``'s document, or ``None``.

    The configured release date wins. Otherwise the latest commit touching
    ``doc_path`` is read from GitHub. A malformed repository slug, an API error
    and an unparseable timestamp all yield ``None``, so a failure to decorate
    the page cannot stop it rendering.

    Parameters
    ----------
    page : PageConfig
        Page whose release and repository details are consulted.
    token : str, optional
        GitHub token for the lookup. The caller reads it from the environment,
        so this module never depends on ambient credentials.
    client : github3.GitHub, optional
        Client to query through; a fresh unauthenticated-or-token client is
        created when omitted.
    """
    if page.latest_release_published_at:
        return page.latest_release_published_at
    return _fetch_doc_commit_date(page, client=client, token=token)


def _fetch_doc_commit_date(
    page: PageConfig, *, client: GitHub | None = None, token: str | None = None
) -> dt.datetime | None:
    """Return the latest commit timestamp for the page repository or None."""
    result: dt.datetime | None = None
    repo_slug = page.repo
    if repo_slug:
        try:
            owner, name = repo_slug.split("/", 1)
        except ValueError:
            owner = name = None

        if owner and name:
            branch = page.branch or "main"
            doc_path = page.doc_path.lstrip("/")
            github = client or GitHub(token=token)
            try:
                repository = github.repository(owner, name)
            except gh_exc.GitHubException:
                repository = None

            if repository is not None:
                try:
                    commits = repository.commits(path=doc_path, sha=branch)
                except gh_exc.GitHubException:
                    commits = None

                if commits is not None:
                    try:
                        latest_commit = next(iter(commits), None)
                    except gh_exc.GitHubException:
                        latest_commit = None
                    if latest_commit:
                        result = _extract_commit_timestamp(latest_commit)

    return result


def _extract_commit_timestamp(commit: object) -> dt.datetime | None:
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
        normalized = _normalize_commit_date(date_value)
        if normalized:
            return normalized
    return None


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
    ) -> None:
        """Initialize the generator with configuration and template context.

        Construction performs no I/O: no document is fetched, no commit date
        is looked up and no output directory is created. The network is
        reached only by :meth:`render`.

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
        """
        self.page = page_config
        self.output_dir_override = output_dir
        default_templates = Path(__file__).resolve().parents[1] / "templates"
        self.templates_dir = templates_dir or default_templates
        self.renderer = HtmlContentRenderer(
            page_config.pygments_style, link_extension=_build_link_rewriter(page_config)
        )
        self._description_resolver = ManifestDescriptionResolver()
        self.env = template_environment(self.templates_dir, escape_by_suffix=True)
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

        This is the command that reaches the network: it fetches the document
        and, when no release date is configured, asks GitHub for the latest
        commit date. Rendering itself is delegated to :meth:`render_document`,
        which is handed the markdown and performs no I/O.

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
        return self.render_document(
            fetched.text,
            source_url=fetched.source_url,
            version_display=_strip_version_prefix(fetched.version),
            updated_at=fetched.updated_at,
            page_description=self._resolve_description(),
        )

    def render_document(
        self,
        markdown: str,
        *,
        source_url: str,
        version_display: str | None,
        page_description: str,
        updated_at: dt.datetime | None = None,
    ) -> RenderedDocument:
        """Render already-fetched markdown into an unpublished bundle.

        The method performs no I/O: it parses ``markdown``, builds the section
        models and renders the templates against the supplied provenance. A
        caller can therefore render a fixture, or re-render a cached document,
        without a network call or an output write.

        Parameters
        ----------
        markdown : str
            The document body to render.
        source_url : str
            URL the document was fetched from, shown in the page chrome.
        version_display : str or None
            Release version without its leading ``v``, or ``None`` when the
            document is not pinned to a release.
        page_description : str
            Description used in the page's metadata tags.
        updated_at : datetime, optional
            Date shown as the document's "Updated" badge; the build time is
            used when omitted.

        Returns
        -------
        RenderedDocument
            The HTML and destination paths ready for the writer.

        Raises
        ------
        RuntimeError
            If the markdown has no second-level sections.
        """
        sections = parse_sections(markdown)
        if not sections:
            msg = "No second-level sections were found in the upstream markdown."
            raise RuntimeError(msg)

        out_dir = self.output_dir_override or self.page.output_dir

        generated_at = build_timestamp()
        doc_updated_at = updated_at or generated_at
        section_bundle: list[tuple[Section, SectionModel, str]] = []
        for section in sections:
            layout = self._resolve_layout(section.slug)
            section_model = self._build_section_model(section, layout)
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
            html = self.env.render_template("doc_page.jinja", **context)
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
        self, section: Section, layout: SectionLayout
    ) -> SectionModel:
        """Construct a SectionModel with rendered HTML and layout metadata."""
        intro_html = self.renderer.markdown(section.intro_markdown)
        default_html = self.renderer.markdown(section.markdown)
        numbered_steps: list[NumberedStep] = []
        split_panel = {"primary_html": "", "secondary_html": ""}
        subsections = self._build_subsection_blocks(section)
        toc_items = [
            {"label": block["title"], "anchor": block["anchor"]}
            for block in subsections
        ]
        resolved_layout = layout.device

        if layout.device == "numbered_steps":
            subsection_anchors = {b["title"]: b["anchor"] for b in subsections}
            numbered_steps = self._prepare_numbered_steps(
                section, layout, subsection_anchors=subsection_anchors
            )
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
        self,
        section: Section,
        layout: SectionLayout,
        *,
        subsection_anchors: dict[str, str] | None = None,
    ) -> list[NumberedStep]:
        """Return numbered step data for ``section`` based on the provided layout.

        Parameters
        ----------
        section : Section
            The parsed markdown section containing subsections.
        layout : SectionLayout
            Layout configuration that may specify a custom step ordering.
        subsection_anchors : dict[str, str] or None, optional
            Mapping of subsection title to content-based anchor string, as
            produced by :meth:`_build_subsection_blocks`.  When provided, each
            step's ``content_anchor`` is set to the corresponding value so that
            nav links and in-page anchors remain consistent.
        """
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

        anchors = subsection_anchors or {}
        steps: list[NumberedStep] = []
        for idx, sub in enumerate(subsections, start=1):
            html = self.renderer.markdown(sub.markdown)
            step_anchor = f"{section.slug}-step-{idx}"
            content_anchor = anchors.get(sub.title, step_anchor)
            steps.append(
                NumberedStep(
                    title=sub.title,
                    number=idx,
                    html=html,
                    anchor=step_anchor,
                    content_anchor=content_anchor,
                )
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
