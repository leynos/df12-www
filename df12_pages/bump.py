"""Helpers for updating latest release metadata inside pages config."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from .releases import GitHubReleaseClient, ReleaseInfo


class PagesConfigError(ValueError):
    """Raised when the layout configuration cannot be updated."""


def bump_latest_release_metadata(
    *, config_path: Path, client: GitHubReleaseClient
) -> dict[str, str | None]:
    """Fetch latest releases for each page repo and update the YAML file.

    Returns a mapping of page keys to the tag recorded (``None`` when no
    release exists). The YAML document is always re-serialized so that removals
    of ``latest_release`` keys are persisted as well.
    """

    yaml = _build_roundtrip_yaml()
    with config_path.open("r", encoding="utf-8") as handle:
        document = yaml.load(handle) or CommentedMap()
    if not isinstance(document, CommentedMap):
        msg = "Top-level configuration must be a mapping"
        raise PagesConfigError(msg)

    defaults = document.get("defaults")
    if not isinstance(defaults, Mapping):
        defaults = {}

    pages = document.get("pages")
    if not isinstance(pages, CommentedMap) or not pages:
        msg = "No pages defined in layout configuration"
        raise PagesConfigError(msg)

    results: dict[str, str | None] = {}
    for key, page_payload in pages.items():
        if not isinstance(page_payload, CommentedMap):
            continue
        repo = _resolve_repo(page_payload, defaults)
        if not repo:
            continue
        release = client.fetch_latest(repo)
        tag = _record_release(page_payload, release)
        results[key] = tag

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
    page_payload: Mapping[str, Any], defaults: Mapping[str, Any]
) -> str | None:
    repo = page_payload.get("repo") or defaults.get("repo")
    if not repo:
        return None
    return str(repo)


def _record_release(page_payload: CommentedMap, release: ReleaseInfo | None) -> str | None:
    if release:
        _upsert_latest_release(page_payload, release.tag_name)
        return release.tag_name
    if "latest_release" in page_payload:
        del page_payload["latest_release"]
    return None


def _upsert_latest_release(page_payload: CommentedMap, tag: str) -> None:
    if "latest_release" in page_payload:
        page_payload["latest_release"] = tag
        return

    insert_index = None
    existing_keys = list(page_payload.keys())
    if "repo" in page_payload:
        insert_index = existing_keys.index("repo") + 1
    elif "language" in page_payload:
        insert_index = existing_keys.index("language") + 1

    if insert_index is None:
        page_payload["latest_release"] = tag
    else:
        page_payload.insert(insert_index, "latest_release", tag)

