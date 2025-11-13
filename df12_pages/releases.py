"""Utilities for interrogating GitHub releases."""

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
    """Minimal metadata captured from a GitHub release object."""

    tag_name: str
    name: str | None = None
    html_url: str | None = None
    published_at: str | None = None


class GitHubReleaseClient:
    """Thin wrapper around the GitHub REST API release endpoints."""

    default_api_base = DEFAULT_API_BASE

    def __init__(
        self,
        *,
        token: str | None = None,
        api_base: str = DEFAULT_API_BASE,
        session: requests.Session | None = None,
        timeout: float = 10.0,
    ) -> None:
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
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)
