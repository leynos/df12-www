"""Regression tests for repository build script wiring."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_build_pages_script_generates_all_sites() -> None:
    """The default build pipeline should refresh main and sub-site outputs."""
    package_json = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    build_pages = package_json["scripts"]["build:pages"]
    assert build_pages == "uv run pages generate --all-sites"
