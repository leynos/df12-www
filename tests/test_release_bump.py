"""Unit tests for the pages bump workflow."""

from __future__ import annotations

import typing as typ
from textwrap import dedent

import requests
from ruamel.yaml import YAML

from df12_pages.bump import bump_latest_release_metadata
from df12_pages.releases import GitHubReleaseClient, ReleaseInfo

if typ.TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


def test_github_release_client_fetches_release_and_uses_token(
    mocker: MockerFixture,
) -> None:
    """The GitHub client should pass auth headers and parse release payloads."""
    session = mocker.Mock(spec=requests.Session)
    response = mocker.Mock()
    response.status_code = 200
    response.json.return_value = {
        "tag_name": "v1.2.3",
        "name": "Release",
        "html_url": "https://example.invalid/releases/1",
        "published_at": "2025-11-01T00:00:00Z",
    }
    session.get.return_value = response

    client = GitHubReleaseClient(
        token="secret-token", api_base="https://example.invalid", session=session
    )
    release = client.fetch_latest("owner/repo")

    assert release is not None, "expected ReleaseInfo when GitHub returns 200"
    assert release.tag_name == "v1.2.3", (
        f"expected tag_name 'v1.2.3', got {release.tag_name!r}"
    )

    session.get.assert_called_once()
    called_url = session.get.call_args.args[0]
    assert called_url == "https://example.invalid/repos/owner/repo/releases/latest", (
        f"expected latest releases endpoint to be requested, got {called_url!r}"
    )
    headers = session.get.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer secret-token", (
        "expected Authorization header to include Bearer token"
    )


def test_github_release_client_returns_none_for_missing_release(
    mocker: MockerFixture,
) -> None:
    """GitHub returns HTTP 404 when no releases exist; treat that as None."""
    session = mocker.Mock(spec=requests.Session)
    response = mocker.Mock()
    response.status_code = 404
    response.text = ""
    session.get.return_value = response

    client = GitHubReleaseClient(session=session)
    assert client.fetch_latest("owner/missing") is None, (
        "expected None for repositories without releases (HTTP 404)"
    )


def test_bump_workflow_updates_yaml(tmp_path: Path) -> None:
    """Latest release values should be inserted or removed per repo."""
    config_path = tmp_path / "pages.yaml"
    config_path.write_text(
        dedent(
            """
            defaults:
              output_dir: public
            pages:
              first:
                repo: owner/alpha
                language: rust
              second:
                repo: owner/beta
                latest_release: prune-me
                latest_release_published_at: 2024-01-01T00:00:00Z
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    class StubClient(GitHubReleaseClient):
        def __init__(self) -> None:
            super().__init__()
            self.calls: list[str] = []

        def fetch_latest(self, repo: str) -> ReleaseInfo | None:
            self.calls.append(repo)
            if repo == "owner/alpha":
                return ReleaseInfo(
                    tag_name="v9.9.9", published_at="2025-11-01T00:00:00Z"
                )
            return None

    client = StubClient()
    result = bump_latest_release_metadata(config_path=config_path, client=client)

    assert result["second"] is None, "expected second repo to remain unset"
    assert result["first"] is not None, "expected first repo release to be set"
    assert result["first"].tag_name == "v9.9.9", (
        f"expected tag_name 'v9.9.9', got {result['first'].tag_name!r}"
    )
    assert result["first"].published_at == "2025-11-01T00:00:00Z", (
        "expected published_at '2025-11-01T00:00:00Z', "
        f"got {result['first'].published_at!r}"
    )
    assert client.calls == ["owner/alpha", "owner/beta"], (
        f"expected client to fetch both repos once, got {client.calls!r}"
    )

    yaml = YAML(typ="safe")
    parsed = yaml.load(config_path.read_text(encoding="utf-8"))
    first_page = parsed["pages"]["first"]
    assert first_page["latest_release"] == "v9.9.9", (
        f"expected latest_release 'v9.9.9', got {first_page.get('latest_release')!r}"
    )
    assert first_page["latest_release_published_at"] == "2025-11-01T00:00:00Z", (
        "expected latest_release_published_at '2025-11-01T00:00:00Z', "
        f"got {first_page.get('latest_release_published_at')!r}"
    )
    assert "latest_release" not in parsed["pages"]["second"], (
        "expected second repo latest_release entry to be removed"
    )
