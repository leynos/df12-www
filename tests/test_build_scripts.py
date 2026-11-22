"""Regression tests for repository build script wiring."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def package_scripts() -> dict[str, str]:
    """Return the build-script mapping from the repository manifest."""
    package_json = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    return package_json["scripts"]


def test_build_pages_script_generates_all_sites(
    package_scripts: dict[str, str],
) -> None:
    """The default build pipeline should refresh main and sub-site outputs."""
    build_pages = package_scripts["build:pages"]
    assert build_pages == "uv run pages generate --all-sites", (
        "build:pages must generate every configured site"
    )


def test_build_css_compiles_the_episodic_entrypoint(
    package_scripts: dict[str, str],
) -> None:
    """The shared CSS pipeline should build Episodic from tracked sources."""
    assert "bun run build:css:episodic" in package_scripts["build:css"], (
        "build:css must invoke the Episodic stylesheet build"
    )
    assert package_scripts["build:css:episodic"] == (
        "bunx tailwindcss -i ./src/styles/episodic.css "
        "-o ./public/episodic/assets/styles/tailwind.css --minify"
    ), "build:css:episodic must publish the configured Episodic Tailwind output"


def test_build_search_generates_once_and_the_check_command_detects_drift(
    package_scripts: dict[str, str],
) -> None:
    """Generation collects one Episodic payload and checking is a separate gate."""
    build_search = package_scripts["build:search"]
    command = "bun run scripts/build-episodic-search-index.mjs"

    assert command in build_search, "build:search must regenerate the Episodic index"
    assert build_search.count(command) == 1, (
        "build:search must collect the Episodic search payload exactly once"
    )
    assert package_scripts["check:search"] == f"{command} --check", (
        "check:search must retain deterministic Episodic index drift verification"
    )


def test_pages_refuses_an_enabled_gil() -> None:
    """Reject GIL-enabled execution before the CLI dispatches any command."""
    result = subprocess.run(
        [sys.executable, "-X", "gil=1", "-c", "from df12_pages import main; main()"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "free-threaded CPython 3.15.2" in result.stderr
