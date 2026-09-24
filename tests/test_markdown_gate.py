"""Contract tests for the Markdown wiring in the ``Makefile``.

These assert how ``make markdownlint`` and ``make fmt`` find and call
``markdownlint-cli2``, not what the linter reports. ``MDLINT`` resolves the
linter from ``PATH`` and falls back to Bun's global bin under ``$HOME``, where
the estate installs it, so that a missing linter is reported by name rather
than leaving ``MDLINT`` empty and the recipe running ``'**/*.md'`` as a
command. ``make fmt`` unsets ``FORCE_COLOR`` for the fixer, as concordat's
baseline does.

Both halves of that depend on ``PATH`` and ``HOME``, so each test runs the real
target with an environment it controls entirely: ``PATH`` holds nothing but a
directory of stub executables, and ``HOME`` is a temporary directory that holds
a stub linter only when the test puts one there. That is why these use stub
scripts rather than cmd-mox. A cmd-mox shim is reached by prepending its
directory to the inherited ``PATH``, which would leave the real linter on the
search path, and the fallback under test is a fixed file path that no ``PATH``
shim can stand in for.

The stubs are ``/bin/sh`` scripts that use only shell builtins, so they run on
the empty ``PATH``. Each appends one line to a shared log naming itself, the
``FORCE_COLOR`` it saw, and its arguments, which records both what each recipe
called and in what order. make is invoked by absolute path, so the nested
``$(MAKE) spelling`` finds it too, and reaches the ``uv`` stub rather than
fetching the spelling tool.
"""

from __future__ import annotations

import dataclasses as dc
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MAKE = shutil.which("make")

#: The name ``MDLINT`` searches ``PATH`` for, and the fallback beneath ``HOME``.
LINTER = "markdownlint-cli2"
FALLBACK = (".bun", "bin", LINTER)

#: What the log records when a stub runs without ``FORCE_COLOR`` set.
UNSET = "<unset>"

#: What ``make markdownlint`` asks the linter to do.
LINT_ARGS = ["**/*.md"]

#: What ``make fmt`` asks the linter to do.
FIX_ARGS = ["--fix", "**/*.md"]

#: The tail of the ``uv`` call the ``spelling`` target makes, which
#: ``markdownlint`` chains after the linter.
SPELLING_TAIL = ["typos-config-builder", "gate", "--repository", "."]

pytestmark = pytest.mark.skipif(MAKE is None, reason="make is not installed")


@dc.dataclass(frozen=True)
class Call:
    """One recorded stub invocation."""

    tool: str
    force_color: str
    args: list[str]


@dc.dataclass(frozen=True)
class Sandbox:
    """The controlled ``PATH`` directory, ``HOME``, and invocation log."""

    bin_dir: Path
    home: Path
    log: Path

    @property
    def fallback(self) -> Path:
        """Return where ``MDLINT`` looks when the linter is not on ``PATH``."""
        return self.home.joinpath(*FALLBACK)

    def stub(self, path: Path, label: str, exit_code: int = 0) -> Path:
        """Write an executable stub at ``path`` that logs under ``label``."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\t%s' '{label}' \"${{FORCE_COLOR-{UNSET}}}\" "
            f'>> "{self.log}"\n'
            f'for arg in "$@"; do printf \'\\t%s\' "$arg" >> "{self.log}"; done\n'
            f"printf '\\n' >> \"{self.log}\"\n"
            f"exit {exit_code}\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def tool(self, name: str, exit_code: int = 0) -> Path:
        """Put a stub called ``name`` on the controlled ``PATH``."""
        return self.stub(self.bin_dir / name, name, exit_code)

    def calls(self, tool: str | None = None) -> list[Call]:
        """Return the recorded invocations, optionally of one tool only."""
        if not self.log.exists():
            return []
        recorded = []
        for line in self.log.read_text(encoding="utf-8").splitlines():
            label, force_color, *args = line.split("\t")
            recorded.append(Call(label, force_color, args))
        return [call for call in recorded if tool is None or call.tool == tool]

    def run(
        self,
        target: str,
        *overrides: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run one make target under the controlled environment."""
        assert MAKE is not None
        return subprocess.run(  # noqa: S603 - fixed argv, no shell
            [MAKE, target, *overrides],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            # Built from nothing rather than from os.environ, so neither an
            # MDLINT nor a FORCE_COLOR in the caller's environment leaks in.
            env={
                "PATH": str(self.bin_dir),
                "HOME": str(self.home),
                "MAKEFLAGS": "",
                **(env or {}),
            },
            check=False,
            timeout=60,
        )


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    """Provide an empty ``PATH`` directory and ``HOME``, with ``uv`` stubbed."""
    box = Sandbox(tmp_path / "bin", tmp_path / "home", tmp_path / "calls.log")
    box.bin_dir.mkdir()
    box.home.mkdir()
    # `markdownlint` ends by running `make spelling`, which calls uv.
    box.tool("uv")
    return box


def _output(result: subprocess.CompletedProcess[str]) -> str:
    """Return a make run's combined output for an assertion message."""
    return f"exit {result.returncode}:\n{result.stdout}{result.stderr}"


def test_markdownlint_uses_the_linter_on_path(sandbox: Sandbox) -> None:
    """``PATH`` wins over the fallback when both hold a linter."""
    sandbox.tool(LINTER)
    sandbox.stub(sandbox.fallback, "fallback")

    result = sandbox.run("markdownlint")

    assert result.returncode == 0, _output(result)
    assert [call.args for call in sandbox.calls(LINTER)] == [LINT_ARGS]
    assert sandbox.calls("fallback") == [], (
        "the fallback should not run when the linter is on PATH"
    )


def test_markdownlint_falls_back_to_bun_global_bin(sandbox: Sandbox) -> None:
    """With nothing on ``PATH``, the linter under ``$HOME/.bun/bin`` runs."""
    sandbox.stub(sandbox.fallback, "fallback")

    result = sandbox.run("markdownlint")

    assert result.returncode == 0, _output(result)
    assert [call.args for call in sandbox.calls("fallback")] == [LINT_ARGS]


def test_markdownlint_runs_spelling_after_a_clean_lint(sandbox: Sandbox) -> None:
    """A passing lint goes on to the spelling gate, in that order."""
    sandbox.tool(LINTER)

    result = sandbox.run("markdownlint")

    assert result.returncode == 0, _output(result)
    calls = sandbox.calls()
    assert [call.tool for call in calls] == [LINTER, "uv"]
    assert calls[1].args[-len(SPELLING_TAIL) :] == SPELLING_TAIL


def test_markdownlint_names_the_missing_linter(sandbox: Sandbox) -> None:
    """With no linter anywhere, the target fails and names what it looked for.

    Before the fallback, ``MDLINT`` was empty here, so the prerequisite check
    was skipped and the recipe tried to execute the glob.
    """
    result = sandbox.run("markdownlint")

    assert result.returncode != 0, _output(result)
    assert f"'{sandbox.fallback}' is required, but not installed" in result.stderr, (
        _output(result)
    )
    assert sandbox.calls() == [], "nothing should run without a linter"


def test_markdownlint_fails_when_the_linter_fails(sandbox: Sandbox) -> None:
    """A linter failure fails the target and stops before spelling."""
    sandbox.tool(LINTER, exit_code=1)

    result = sandbox.run("markdownlint")

    assert result.returncode != 0, _output(result)
    assert [call.tool for call in sandbox.calls()] == [LINTER]


def _run_fmt(sandbox: Sandbox, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    """Run ``make fmt`` with every tool it calls stubbed.

    ``RUFF`` names a path in the virtualenv rather than a command, and the
    ``node_modules`` stamp would run ``bun install`` and then ``touch`` inside
    the checkout when stale, so both are pointed into the sandbox instead.
    ``FORCE_COLOR`` is set, so the test can see who receives it.
    """
    for tool in ("bun", "mdtablefix", "ruff"):
        sandbox.tool(tool)
    stamp = tmp_path / "install-stamp"
    stamp.touch()
    return sandbox.run(
        "fmt",
        f"RUFF={sandbox.bin_dir / 'ruff'}",
        f"NODE_MODULES_STAMP={stamp}",
        env={"FORCE_COLOR": "1"},
    )


def test_fmt_runs_the_fixer_last_without_force_color(
    sandbox: Sandbox, tmp_path: Path
) -> None:
    """``make fmt`` ends with ``--fix`` and hides ``FORCE_COLOR`` from it alone.

    The other tools still see ``FORCE_COLOR=1``, which shows the variable did
    reach the recipe, so its absence at the linter is the recipe's doing.
    """
    sandbox.tool(LINTER)

    result = _run_fmt(sandbox, tmp_path)

    assert result.returncode == 0, _output(result)
    calls = sandbox.calls()
    assert calls[-1] == Call(LINTER, UNSET, FIX_ARGS), calls
    assert calls[-2].tool == "mdtablefix", "mdtablefix should run before the fixer"
    assert all(call.force_color == "1" for call in calls[:-1]), calls


def test_fmt_fails_when_the_fixer_fails(sandbox: Sandbox, tmp_path: Path) -> None:
    """A fixer failure fails ``make fmt`` despite the preceding ``unset``."""
    sandbox.tool(LINTER, exit_code=1)

    result = _run_fmt(sandbox, tmp_path)

    assert result.returncode != 0, _output(result)
    assert sandbox.calls()[-1].tool == LINTER
