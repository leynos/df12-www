"""Contract tests for ``.markdownlint-cli2.jsonc``.

The file copies the estate baseline verbatim from leynos/concordat's
``platform-standards/canon/lint/markdown/.markdownlint-cli2.jsonc``, which
concordat's ``markdown-formatting-baseline`` rule audits, and appends the
ignores this repository needs on top. So the contract has three parts: the
canonical rules and ignores are present unaltered and in order, the local
ignores follow them, and nothing waives a rule the baseline enforces, as the
``MD036`` waiver this file used to carry did.

Asserting the entries alone would only prove the file says what it says, so
the rest run the real linter over fixtures in a temporary directory, never
the checkout. Every ignore gets a probe that breaks a rule and is ignored
under the shipped file, and the same probe is linted once the entries
covering it are dropped, so a pass is the ignore doing the work rather than
the probe being clean or the linter skipping the directory by default.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import typing as typ
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG = REPO_ROOT / ".markdownlint-cli2.jsonc"

#: concordat's canonical ``config`` block. ``MD036`` is enabled by default and
#: the baseline does not waive it.
CANONICAL_RULES: dict[str, typ.Any] = {
    "MD004": {"style": "dash"},
    "MD010": {"code_blocks": False},
    "MD013": {
        "line_length": 80,
        "code_block_line_length": 120,
        "tables": False,
        "headings": False,
    },
    "MD029": {"style": "ordered"},
}

#: concordat's canonical ``ignores``, which the file must open with.
CANONICAL_IGNORES = [
    "**/.venv/**",
    ".vtcode/**",
    "**/node_modules/**",
    "**/target/**",
    ".terraform/**",
    ".uv-cache/**",
    "memories/**",
    "CRUSH.md",
]

#: The ignores this repository adds after the canonical ones.
LOCAL_IGNORES = ["**/.terraform/**", ".bun_tmp/**", "**/.uv-tools/**"]

#: A probe path for each ignore, and every entry that covers it. Dropping all
#: of them is what makes the probe linted again; the root ``.terraform`` is
#: matched by the canonical entry and by the local nested one alike.
PROBES = [
    ("sub/.venv/probe.md", ["**/.venv/**"]),
    (".vtcode/probe.md", [".vtcode/**"]),
    ("sub/node_modules/probe.md", ["**/node_modules/**"]),
    ("sub/target/probe.md", ["**/target/**"]),
    (".terraform/probe.md", [".terraform/**", "**/.terraform/**"]),
    (".uv-cache/probe.md", [".uv-cache/**"]),
    ("memories/probe.md", ["memories/**"]),
    ("CRUSH.md", ["CRUSH.md"]),
    ("modules/site/tests/.terraform/probe.md", ["**/.terraform/**"]),
    (".bun_tmp/probe.md", [".bun_tmp/**"]),
    ("sub/.uv-tools/probe.md", ["**/.uv-tools/**"]),
]

#: Breaks ``MD004``: the baseline wants dashes for list items.
UNORDERED_STAR = "# Probe\n\n* item\n"

#: The emphasis-only label ``MD036`` rejects, and the plain text it became.
EMPHASIS_LABEL = "# Guide\n\n*Last updated: 2026-09-24*\n\nBody text.\n"
PLAIN_LABEL = "# Guide\n\nLast updated: 2026-09-24\n\nBody text.\n"


def _linter() -> str | None:
    """Resolve the linter as ``MDLINT`` does: ``PATH``, then Bun's global bin."""
    fallback = Path.home() / ".bun" / "bin" / "markdownlint-cli2"
    return shutil.which("markdownlint-cli2") or (
        str(fallback) if os.access(fallback, os.X_OK) else None
    )


LINTER = _linter()

needs_linter = pytest.mark.skipif(
    LINTER is None, reason="markdownlint-cli2 is not installed"
)


def _load_config() -> dict[str, typ.Any]:
    """Parse the JSONC file, whose comments all sit on lines of their own."""
    lines = CONFIG.read_text(encoding="utf-8").splitlines()
    return json.loads(
        "\n".join(line for line in lines if not line.lstrip().startswith("//"))
    )


def _lint(root: Path) -> subprocess.CompletedProcess[str]:
    """Run the real linter over every Markdown file beneath ``root``."""
    assert LINTER is not None
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [LINTER, "**/*.md"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def _write(root: Path, relative: str, text: str) -> None:
    """Write a fixture file, creating its parent directories."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_the_rules_are_the_canonical_ones_and_waive_nothing() -> None:
    """The ``config`` block is concordat's, with no ``MD036`` waiver."""
    config = _load_config()

    assert config["config"] == CANONICAL_RULES
    assert "MD036" not in config["config"]


def test_the_ignores_are_canonical_then_local() -> None:
    """The canonical ignores open the list in order; the local ones follow."""
    ignores = _load_config()["ignores"]

    assert ignores[: len(CANONICAL_IGNORES)] == CANONICAL_IGNORES
    assert ignores[len(CANONICAL_IGNORES) :] == LOCAL_IGNORES


def test_every_ignore_has_a_probe() -> None:
    """No ignore entry goes untested by the probes below."""
    covered = {entry for _, entries in PROBES for entry in entries}

    assert covered == set(CANONICAL_IGNORES + LOCAL_IGNORES)


@needs_linter
@pytest.mark.parametrize(("probe", "entries"), PROBES)
def test_an_ignored_tree_is_skipped_and_linted_without_its_entry(
    tmp_path: Path, probe: str, entries: list[str]
) -> None:
    """The shipped file ignores the probe; without its entries it is linted."""
    _write(tmp_path, probe, UNORDERED_STAR)
    shutil.copyfile(CONFIG, tmp_path / CONFIG.name)

    shipped = _lint(tmp_path)
    assert shipped.returncode == 0, shipped.stdout + shipped.stderr

    config = _load_config()
    config["ignores"] = [entry for entry in config["ignores"] if entry not in entries]
    (tmp_path / CONFIG.name).write_text(json.dumps(config), encoding="utf-8")

    uncovered = _lint(tmp_path)
    assert uncovered.returncode != 0, (
        f"{probe} should be linted once {entries} are dropped"
    )
    assert "MD004" in uncovered.stdout + uncovered.stderr


@needs_linter
def test_an_emphasis_only_label_fails_and_plain_text_passes(tmp_path: Path) -> None:
    """``MD036`` is enforced now its waiver is gone."""
    shutil.copyfile(CONFIG, tmp_path / CONFIG.name)
    _write(tmp_path, "docs/guide.md", EMPHASIS_LABEL)

    emphasised = _lint(tmp_path)
    assert emphasised.returncode != 0
    assert "MD036" in emphasised.stdout + emphasised.stderr

    _write(tmp_path, "docs/guide.md", PLAIN_LABEL)
    plain = _lint(tmp_path)
    assert plain.returncode == 0, plain.stdout + plain.stderr
