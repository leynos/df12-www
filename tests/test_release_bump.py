"""Unit tests for the pages bump workflow."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import requests
from pytest_mock import MockerFixture
from ruamel.yaml import YAML

from df12_pages.bump import bump_latest_release_metadata
from df12_pages.releases import GitHubReleaseClient, ReleaseInfo


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

    assert release is not None
    assert release.tag_name == "v1.2.3"

    session.get.assert_called_once()
    called_url = session.get.call_args.args[0]
    assert called_url == "https://example.invalid/repos/owner/repo/releases/latest"
    headers = session.get.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer secret-token"


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
    assert client.fetch_latest("owner/missing") is None


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

    assert result["second"] is None
    assert result["first"] is not None
    assert result["first"].tag_name == "v9.9.9"
    assert result["first"].published_at == "2025-11-01T00:00:00Z"
    assert client.calls == ["owner/alpha", "owner/beta"]

    yaml = YAML(typ="safe")
    parsed = yaml.load(config_path.read_text(encoding="utf-8"))
    assert parsed["pages"]["first"]["latest_release"] == "v9.9.9"
    assert (
        parsed["pages"]["first"]["latest_release_published_at"]
        == "2025-11-01T00:00:00Z"
    )
    assert "latest_release" not in parsed["pages"]["second"]
