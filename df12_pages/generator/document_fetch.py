"""Resolve and fetch the markdown a documentation page is built from.

Fetching is a command with a value result. :func:`resolve_document_source`
turns a page's configuration into the candidate URLs, and
:func:`fetch_document` tries them in order and returns the body together with
the URL, version and date that actually answered.

Keeping this work away from the generator lets a render be exercised against
recorded provenance with no network, and leaves
:mod:`df12_pages.generator.page_generator` owning only the generator and the
rendered-document types.
"""

from __future__ import annotations

import dataclasses as dc
import datetime as dt
import email.utils
import typing as typ

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

if typ.TYPE_CHECKING:
    from df12_pages.config import PageConfig

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
    """A markdown body and the provenance that actually answered for it.

    ``updated_at`` is the date to display for the document, if any. It is the
    caller's release or commit date when that applies to the URL that
    answered, and otherwise the response's ``Last-Modified`` date.
    """

    text: str
    source_url: str
    version: str | None = None
    updated_at: dt.datetime | None = None


@dc.dataclass(frozen=True)
class MarkdownResponse:
    """A markdown response body with the source date it carried, if any."""

    text: str
    updated_at: dt.datetime | None = None


class DocumentFetcher(typ.Protocol):
    """A callable that fetches one document source."""

    def __call__(
        self, source: DocumentSource, *, updated_at: dt.datetime | None = None
    ) -> FetchedMarkdown:
        """Fetch ``source``, returning its text and provenance."""
        ...


def _strip_version_prefix(tag: str | None) -> str | None:
    """Strip a leading ``v`` or ``V`` if more follows; ``None`` if empty."""
    if not tag:
        return None
    if tag.upper().startswith("V") and len(tag) > 1:
        return tag[1:]
    return tag


def _build_release_url(repo: str, tag: str, path: str) -> str:
    """Return the raw GitHub URL for the file at ``path`` within a tagged release."""
    normalized = path.lstrip("/")
    return f"https://raw.githubusercontent.com/{repo}/refs/tags/{tag}/{normalized}"


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
) -> MarkdownResponse:
    """Download one URL and return its body with the date it last changed.

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
    MarkdownResponse
        The response body and its parsed ``Last-Modified`` date. The date is
        ``None`` when the response omits the header or sends one that cannot be
        parsed, so a malformed header can never fail the build.

    Raises
    ------
    requests.RequestException
        If the request fails at the transport level, or if the response is an
        HTTP error. Failures are raised rather than replaced with empty text,
        so a missing document cannot be published as a blank page.
    """
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return MarkdownResponse(
        text=response.text,
        updated_at=_last_modified(response.headers.get("Last-Modified")),
    )


def _last_modified(value: str | None) -> dt.datetime | None:
    """Parse an HTTP ``Last-Modified`` value into a UTC datetime, if valid."""
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except TypeError, ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


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
    its date may claim to belong to that release. The branch response's own
    ``Last-Modified`` date takes its place, so the page still shows when the
    document it displays last changed.

    Parameters
    ----------
    source : DocumentSource
        Candidate URLs, pinned release first.
    updated_at : datetime, optional
        Date already known for the document, used only when the release-pinned
        attempt is the one that answered.
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
                response = fetch_markdown(url, session=active)
            except requests.HTTPError as error:
                last_attempt = index == len(attempts) - 1
                if last_attempt or _http_status(error) != requests.codes.not_found:
                    raise
                continue
            known_date = updated_at if index == 0 else None
            return FetchedMarkdown(
                text=response.text,
                source_url=url,
                version=version,
                updated_at=known_date or response.updated_at,
            )
    finally:
        if owned:
            active.close()
    msg = "a document source must offer at least one URL"
    raise AssertionError(msg)


__all__ = [
    "FETCH_TIMEOUT_SECONDS",
    "DocumentFetcher",
    "DocumentSource",
    "FetchedMarkdown",
    "MarkdownResponse",
    "fetch_document",
    "fetch_markdown",
    "resolve_document_source",
]
