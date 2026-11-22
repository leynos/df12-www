"""Select the date to display for a documentation page.

A page's date comes from one of three places, in order of preference: the
release's publication date recorded in the site configuration, the timestamp
of the latest commit touching the document, or the fetched response's own
``Last-Modified`` header. This module owns the first two; the third is read
while fetching, in :mod:`df12_pages.generator.document_fetch`.

Selecting the date is a query and fetching the commit that supplies one is a
command. :func:`resolve_doc_updated_at` reads only its arguments: the page
configuration and a commit payload the caller has already fetched, or
``None`` when there is none. :func:`fetch_latest_doc_commit` is the command
that reaches GitHub for that payload. Keeping them apart lets the selection
be exercised without a client, and makes the only code that talks to GitHub
name the network call.

A page with no repository, a malformed slug and an unparseable timestamp yield
``None``; a GitHub error is raised by the command, so the caller knows the
difference between "there is no date" and "the date could not be read". The
caller that reaches the network owns the policy that a failed lookup must not
stop a page rendering, and logs it where the page key is known.
"""

from __future__ import annotations

import datetime as dt
import typing as typ

if typ.TYPE_CHECKING:
    from github3 import GitHub

    from df12_pages.config import PageConfig


def resolve_doc_updated_at(
    page: PageConfig,
    *,
    commit: object | None,
) -> dt.datetime | None:
    """Select the date to show for ``page``'s document, or ``None``.

    This is a query. It reads the page configuration and the commit payload
    it is given, and returns a value without reaching GitHub or any other
    service. The configured release date wins over the commit date, and an
    unparseable commit timestamp yields ``None``.

    Parameters
    ----------
    page : PageConfig
        Page whose configured release date is preferred.
    commit : object or None
        Latest commit touching the document, as returned by
        :func:`fetch_latest_doc_commit`, or ``None`` when there is none.

    Returns
    -------
    datetime or None
        The configured release date when there is one, otherwise the
        commit's author, then committer, timestamp normalized to UTC.
    """
    if page.latest_release_published_at:
        return page.latest_release_published_at
    if commit is None:
        return None
    return _extract_commit_timestamp(commit)


def fetch_latest_doc_commit(page: PageConfig, *, client: GitHub) -> object | None:
    """Fetch the newest commit touching ``page``'s document, or ``None``.

    This is the command that reaches GitHub; the caller builds ``client`` at
    its own boundary and decides how to report a failure. A page whose
    repository slug is missing or malformed yields ``None`` without a request.

    Parameters
    ----------
    page : PageConfig
        Page whose repository, document path and branch are read.
    client : github3.GitHub
        Client to query through.

    Returns
    -------
    object or None
        The latest commit object, or ``None`` when the page names no readable
        repository or the repository has no commits for the document path.

    Raises
    ------
    github3.exceptions.GitHubException
        If GitHub cannot answer the lookup. Whether that is fatal is the
        caller's decision; this command reports it rather than hiding it.
    """
    owner, name = _repository_parts(page.repo)
    if owner is None or name is None:
        return None
    return _latest_commit(
        client,
        owner,
        name,
        path=page.doc_path.lstrip("/"),
        branch=page.branch or "main",
    )


def _repository_parts(slug: str | None) -> tuple[str | None, str | None]:
    """Split an ``owner/name`` slug, returning two ``None``s when malformed.

    Exactly one slash separates the owner from the name. A slug with an empty
    side or extra components names no repository, so it is rejected here
    rather than passed to GitHub as a repository name containing a slash.
    """
    if not slug:
        return None, None
    owner, _, name = slug.partition("/")
    if not owner or not name or "/" in name:
        return None, None
    return owner, name


def _latest_commit(
    client: GitHub, owner: str, name: str, *, path: str, branch: str
) -> object | None:
    """Return the newest commit touching ``path`` on ``branch``, if any.

    The repository lookup, the commit listing and the first item of that
    listing share one boundary. A GitHub error in any of them escapes as a
    single failure, which the caller can report once instead of reconciling
    three separately swallowed ones.
    """
    repository = client.repository(owner, name)
    if repository is None:
        return None
    commits = repository.commits(path=path, sha=branch)
    return next(iter(commits), None)


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


__all__ = ["fetch_latest_doc_commit", "resolve_doc_updated_at"]
