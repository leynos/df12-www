"""Contract tests for the ``stylelint`` make target.

These assert the wiring rather than the rules. ``stylelint.config.js`` can be
correct and the stylesheets clean while ``make stylelint`` runs nothing at all,
which is how the CSS went unlinted for as long as it did: Biome was configured
long before anything invoked it. A test that only checked the tree is currently
clean would pass just as happily against a target that never calls the linter.

So ``bun`` is replaced with a cmd-mox double and the target is run for real.
The double records what the recipe asked for and dictates how it exits, which
pins both halves of the contract: that ``make stylelint`` reaches the linter,
and that a linter failure fails the target rather than being swallowed.

Mocking ``bun`` rather than ``stylelint`` is deliberate. ``bun run`` puts
``node_modules/.bin`` at the head of ``PATH``, ahead of the shim directory, so
a ``stylelint`` double would never be reached. ``bun`` is the boundary the
Makefile itself crosses, and it is the boundary worth pinning;
:func:`test_the_lint_css_script_runs_stylelint` closes the remaining gap
between ``bun run lint:css`` and the linter.
"""

from __future__ import annotations

import json
import os
import subprocess
import typing as typ
from pathlib import Path

import pytest

if typ.TYPE_CHECKING:
    from cmd_mox import CmdMox

REPO_ROOT = Path(__file__).resolve().parents[1]

#: What the `stylelint` recipe is expected to ask `bun` to do.
LINT_CSS_ARGS = ["run", "lint:css"]

#: `make test` may run under a parent make, whose MAKEFLAGS would otherwise be
#: inherited and change how the nested invocation behaves.
MAKE_ENV = {"MAKEFLAGS": ""}


def _run_make(target: str) -> subprocess.CompletedProcess[str]:
    """Run one make target in the repository root and capture how it exited."""
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["make", target],  # noqa: S607 - make is resolved from PATH by design
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, **MAKE_ENV},
        check=False,
        timeout=120,
    )


def _bun_calls(spy: typ.Any) -> list[list[str]]:  # noqa: ANN401 - cmd-mox double
    """Return every argument list the recipe passed to ``bun``."""
    return [list(invocation.args) for invocation in spy.invocations]


def test_the_target_invokes_stylelint_through_bun(cmd_mox: CmdMox) -> None:
    """``make stylelint`` reaches the linter rather than doing nothing.

    The target may also refresh the ``node_modules`` stamp, which calls ``bun``
    too, so the assertion is that the lint invocation is among the calls and
    not that it is the only one.
    """
    spy = cmd_mox.spy("bun").returns(exit_code=0)

    result = _run_make("stylelint")

    calls = _bun_calls(spy)
    assert LINT_CSS_ARGS in calls, (
        f"`make stylelint` should run `bun {' '.join(LINT_CSS_ARGS)}`; "
        f"it called bun with {calls}"
    )
    assert result.returncode == 0, (
        f"`make stylelint` should pass when the linter passes; "
        f"it exited {result.returncode}:\n{result.stdout}{result.stderr}"
    )


def test_the_target_fails_when_stylelint_fails(cmd_mox: CmdMox) -> None:
    """A linter failure fails the gate, rather than being swallowed.

    This is the assertion that makes the target a gate. A recipe that ignored
    the exit status, or that ended in a command whose status make does not
    see, would satisfy the invocation test above and still let a stylesheet
    with lint errors through `make all`.
    """
    cmd_mox.spy("bun").returns(stderr="stylelint: 1 problem\n", exit_code=1)

    result = _run_make("stylelint")

    assert result.returncode != 0, (
        "`make stylelint` should fail when stylelint reports a problem; "
        f"it exited 0:\n{result.stdout}{result.stderr}"
    )


def test_the_lint_css_script_runs_stylelint() -> None:
    """The script `bun run lint:css` resolves to is the linter itself.

    The two tests above stop at the ``bun`` boundary, so this one closes the
    chain: without it, `lint:css` could be renamed or repointed at something
    else and the mocked invocation would still match.
    """
    manifest = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    script = manifest["scripts"]["lint:css"]

    assert script.startswith("stylelint "), (
        f"`lint:css` should invoke stylelint directly; it is {script!r}"
    )
    assert "src/**/*.css" in script, (
        f"`lint:css` should cover the tracked stylesheets under src/; it is {script!r}"
    )


def test_the_gate_is_chained_into_make_all() -> None:
    """`make all` runs the stylelint target.

    A gate nothing calls is not a gate. `all` is what the contributor guide
    and CI both invoke, so the target's membership of it is part of the
    contract rather than an implementation detail.
    """
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    all_rule = next(line for line in makefile.splitlines() if line.startswith("all:"))

    assert "stylelint" in all_rule.split(), (
        f"`stylelint` should be a prerequisite of `all`; the rule is {all_rule!r}"
    )


@pytest.mark.parametrize("target", ["stylelint", "fmt"])
def test_the_makefile_declares_the_targets_phony(target: str) -> None:
    """Both targets that drive stylelint are phony.

    Neither produces a file of its own name. Were `stylelint` to lose its
    `.PHONY` entry, a stray file called `stylelint` in the repository root
    would make it a no-op that reports success.
    """
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    phony = makefile.split(".PHONY:", 1)[1].split("\n\n", 1)[0]

    assert target in phony.replace("\\\n", " ").split(), (
        f"`{target}` should be listed in .PHONY"
    )
