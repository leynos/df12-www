"""Helpers for updating release metadata in site configuration files.

This module fetches the latest GitHub release tag for each documentation
page defined in a ``pages.yaml`` site configuration and persists that
release metadata back into the YAML. The primary entry point is
``bump_latest_release_metadata``, which accepts a ``pathlib.Path`` to the
config file and an instantiated :class:`GitHubReleaseClient`. It returns a
mapping of page keys to :class:`ReleaseInfo` objects (or ``None`` when a
repository has no releases), allowing callers to verify which pages were
updated.

Example
-------
.. code-block:: python

    from pathlib import Path
    from df12_pages.bump import bump_latest_release_metadata
    from df12_pages.releases import GitHubReleaseClient

    client = GitHubReleaseClient(token="ghp_exampletoken", api_base="https://api.github.com")
    results = bump_latest_release_metadata(
        config_path=Path("config/pages.yaml"),
        client=client,
    )
    for page, info in results.items():
        if info:
            print(f"{page} -> {info.tag_name}")

"""

from __future__ import annotations

import collections.abc as cabc
import typing as typ

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

if typ.TYPE_CHECKING:
    from pathlib import Path

    from .releases import GitHubReleaseClient, ReleaseInfo


class PagesConfigError(ValueError):
    """Raised when the layout configuration cannot be updated."""


def bump_latest_release_metadata(
    *, config_path: Path, client: GitHubReleaseClient
) -> dict[str, ReleaseInfo | None]:
    """Fetch latest releases for each page repo and update the YAML file.

    Returns a mapping of page keys to their recorded :class:`ReleaseInfo`
    (``None`` when no release exists). The YAML document is always re-serialized
    so that removals of release metadata are persisted as well.
    """
    yaml = _build_roundtrip_yaml()
    with config_path.open("r", encoding="utf-8") as handle:
        document = yaml.load(handle) or CommentedMap()
    if not isinstance(document, CommentedMap):
        msg = "Top-level configuration must be a mapping"
        raise PagesConfigError(msg)

    defaults = document.get("defaults")
    if not isinstance(defaults, cabc.Mapping):
        defaults = {}

    pages = document.get("pages")
    if not isinstance(pages, CommentedMap) or not pages:
        msg = "No pages defined in layout configuration"
        raise PagesConfigError(msg)

    results: dict[str, ReleaseInfo | None] = {}
    for key, page_payload in pages.items():
        if not isinstance(page_payload, CommentedMap):
            continue
        repo = _resolve_repo(page_payload, defaults)
        if not repo:
            continue
        release = client.fetch_latest(repo)
        stored = _record_release(page_payload, release)
        results[key] = stored

    with config_path.open("w", encoding="utf-8") as handle:
        yaml.dump(document, handle)

    return results


def _build_roundtrip_yaml() -> YAML:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 120
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def _resolve_repo(
    page_payload: cabc.Mapping[str, typ.Any], defaults: cabc.Mapping[str, typ.Any]
) -> str | None:
    repo = page_payload.get("repo") or defaults.get("repo")
    if not repo:
        return None
    return str(repo)


def _record_release(
    page_payload: CommentedMap, release: ReleaseInfo | None
) -> ReleaseInfo | None:
    if release:
        _upsert_key(
            page_payload, "latest_release", release.tag_name, ("repo", "language")
        )
        if release.published_at:
            _upsert_key(
                page_payload,
                "latest_release_published_at",
                release.published_at,
                ("latest_release", "repo", "language"),
            )
        elif "latest_release_published_at" in page_payload:
            del page_payload["latest_release_published_at"]
        return release

    for key in ("latest_release", "latest_release_published_at"):
        if key in page_payload:
            del page_payload[key]
    return None


def _upsert_key(
    page_payload: CommentedMap, key: str, value: str, anchors: tuple[str, ...]
) -> None:
    if key in page_payload:
        page_payload[key] = value
        return

    insert_index = None
    existing_keys = list(page_payload.keys())
    for anchor in anchors:
        if anchor in page_payload:
            insert_index = existing_keys.index(anchor) + 1
            break

    if insert_index is None:
        page_payload[key] = value
    else:
        page_payload.insert(insert_index, key, value)
