r"""Utilities for interrogating GitHub releases.

This module wraps the portions of the GitHub REST API needed to fetch release
metadata for df12 deployments. It exposes helper classes to retrieve the
latest release tag, surface HTTP errors, and normalise GitHub payloads into
project-friendly dataclasses.

Example
-------
>>> from df12_pages.releases import GitHubReleaseClient
>>> client = GitHubReleaseClient(token="ghp_example", timeout=5)  # doctest: +SKIP
>>> latest = client.fetch_latest("psf/requests")  # doctest: +SKIP
>>> latest.tag_name  # doctest: +SKIP
'v2.32.3'
"""

from __future__ import annotations

import dataclasses as dc
import json
from http import HTTPStatus

import requests

DEFAULT_API_BASE = "https://api.github.com"
_ACCEPT_HEADER = "application/vnd.github+json"


class GitHubReleaseError(RuntimeError):
    """Raised when the GitHub API returns an unexpected error response."""


@dc.dataclass(slots=True)
class ReleaseInfo:
    """Metadata captured from a GitHub release object.

    Attributes
    ----------
    tag_name : str
        Git tag associated with the release.
    name : str | None
        Human-friendly release title if provided.
    html_url : str | None
        URL to the release page for user-facing navigation.
    published_at : str | None
        ISO8601 timestamp indicating when the release was published.
    """

    tag_name: str
    name: str | None = None
    html_url: str | None = None
    published_at: str | None = None


class GitHubReleaseClient:
    """Thin wrapper around GitHub release endpoints.

    This client centralises authentication, timeouts, and error handling when
    querying ``/repos/:owner/:repo/releases`` in the GitHub REST API. It is
    lightweight and safe to reuse across threads when the provided session is
    thread-safe.
    """

    default_api_base = DEFAULT_API_BASE

    def __init__(
        self,
        *,
        token: str | None = None,
        api_base: str = DEFAULT_API_BASE,
        session: requests.Session | None = None,
        timeout: float = 10.0,
    ) -> None:
        """Initialise the client with optional authentication and transport.

        Parameters
        ----------
        token : str | None, optional
            Personal access token or GitHub app token; enables higher rate
            limits and private repo access when provided. Defaults to ``None``.
        api_base : str, optional
            Base URL for the GitHub API; override for GitHub Enterprise
            instances. Defaults to ``DEFAULT_API_BASE``.
        session : requests.Session, optional
            Preconfigured ``requests.Session`` to reuse connections. Defaults
            to a new session per client.
        timeout : float, optional
            Per-request timeout in seconds. Defaults to ``10.0``.

        Notes
        -----
        When ``token`` is provided the appropriate ``Authorization`` header is
        added. The client does not retry failed requests; callers should wrap
        usage in higher-level retry logic if desired.
        """
        self._token = token
        self._api_base = api_base.rstrip("/") or DEFAULT_API_BASE
        self._session = session or requests.Session()
        self.timeout = timeout
        self._headers = {
            "Accept": _ACCEPT_HEADER,
            "User-Agent": "df12-pages/0.1",
        }
        if token:
            self._headers["Authorization"] = f"Bearer {token}"

    def fetch_latest(self, repo: str) -> ReleaseInfo | None:
        """Return the latest non-draft release for ``owner/repo``.

        Parameters
        ----------
        repo:
            Repository identifier in ``owner/name`` form.

        Returns
        -------
        ReleaseInfo | None
            The newest release, or ``None`` when no releases exist (GitHub
            responds with HTTP 404 in that case).
        """
        normalized = repo.strip()
        if not normalized:
            msg = "Repository name cannot be empty"
            raise ValueError(msg)

        url = f"{self._api_base}/repos/{normalized}/releases/latest"
        try:
            response = self._session.get(
                url, headers=self._headers, timeout=self.timeout
            )
        except requests.RequestException as exc:  # pragma: no cover - requests guard
            msg = f"Failed to reach GitHub releases for '{normalized}': {exc}"
            raise GitHubReleaseError(msg) from exc

        if response.status_code == HTTPStatus.NOT_FOUND:
            return None
        if response.status_code >= HTTPStatus.BAD_REQUEST:
            snippet = response.text[:200]
            msg = (
                f"GitHub release lookup for '{normalized}' failed with "
                f"status {response.status_code}: {snippet}"
            )
            raise GitHubReleaseError(msg)

        try:
            payload = response.json()
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            msg = f"GitHub response for '{normalized}' was not valid JSON"
            raise GitHubReleaseError(msg) from exc

        tag_name = _coerce_str(payload.get("tag_name"))
        if not tag_name:
            return None

        return ReleaseInfo(
            tag_name=tag_name,
            name=_coerce_str(payload.get("name")),
            html_url=_coerce_str(payload.get("html_url")),
            published_at=_coerce_str(payload.get("published_at")),
        )


def _coerce_str(value: object) -> str | None:
    """Return the string representation of ``value`` or None."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)
