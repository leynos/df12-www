"""Resolve the date to display for a documentation page.

A page's date comes from one of three places, in order of preference: the
release's publication date recorded in the site configuration, the timestamp
of the latest commit touching the document, or the fetched response's own
``Last-Modified`` header. This module owns the first two; the third is read
while fetching, in :mod:`df12_pages.generator.document_fetch`.

Every lookup here is best effort. A malformed repository slug, a GitHub error
and an unparseable timestamp all yield ``None``, so failing to decorate a page
with a date can never stop it rendering.
"""

from __future__ import annotations

import datetime as dt
import typing as typ

from github3 import GitHub
from github3 import exceptions as gh_exc

if typ.TYPE_CHECKING:
    from df12_pages.config import PageConfig


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


__all__ = ["resolve_doc_updated_at"]
