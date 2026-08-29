"""The argv the harness hands css-view and agent-browser.

Built by pure functions, so what a command would run can be asserted without
starting a browser — which is the only way to catch a flag in the wrong place
or a session two runs would share.
"""

from __future__ import annotations

import os
import subprocess
import typing as typ
from pathlib import Path

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from tests.support.weaver_harness import load

paths = load("weaver_snapshot_paths")
tools = load("weaver_snapshot_tools")


def test_the_css_view_argv_pins_the_browser_and_names_the_output() -> None:
    """A comparison is only meaningful if both sides rendered the same way."""
    argv = tools._css_view_argv(
        "/usr/bin/bun", "http://127.0.0.1:8099", "commands/act/", Path("/out")
    )

    assert argv[:2] == ["/usr/bin/bun", "x"], (
        f"css-view is run through bun; argv starts {argv[:2]!r}"
    )
    assert "--browser" in argv, (
        "the engine must be pinned rather than left to css-view's default, or "
        f"a change to that default silently reshapes the comparison: {argv!r}"
    )
    assert argv[argv.index("--browser") + 1] == "chromium", (
        f"the pinned engine should be chromium; got {argv!r}"
    )
    assert argv[argv.index("--output") + 1] == str(Path("/out/commands__act.json")), (
        f"the snapshot should be named after the page's slug; got {argv!r}"
    )
    assert argv[-1] == "http://127.0.0.1:8099/weaver/commands/act/", (
        f"the page URL is the final positional argument; got {argv[-1]!r}"
    )


def test_the_screenshot_path_precedes_its_flags() -> None:
    """Order is load-bearing here, and getting it wrong still reports success.

    Passing ``--full`` first makes agent-browser read the path as a selector
    and write the image somewhere else, exiting zero either way. Only the
    argument order distinguishes the two.
    """
    argv = tools._screenshot_argv(Path("/out/home@360.png"))

    assert argv[0] == "screenshot", f"the subcommand comes first; got {argv!r}"
    assert argv[1] == "/out/home@360.png", (
        f"the path is positional and must precede any flag; got {argv!r}"
    )
    assert Path(argv[1]).is_absolute(), (
        "agent-browser runs as a daemon with its own working directory, so a "
        f"relative path would land somewhere unexpected; got {argv[1]!r}"
    )


def test_concurrent_runs_do_not_share_a_browser_session() -> None:
    """A shared session name would let two runs interleave.

    agent-browser sessions are named globally and hold one viewport and one
    current page between calls, so two runs sharing a name would resize each
    other's viewport mid-capture and report success for both.
    """
    name = tools._session_name()

    assert str(os.getpid()) in name, (
        f"the session name must distinguish this process; got {name!r}"
    )
    assert name.startswith("weaver-shots"), (
        f"the name should still say what the session is for; got {name!r}"
    )


def test_capture_drives_one_tool_run_per_page() -> None:
    """Page discovery feeds the runner, and nothing is silently skipped."""
    calls: list[list[str]] = []
    pages = ["", "install/", "commands/act/"]
    tools._capture_pages(
        pages,
        Path("/out"),
        "http://127.0.0.1:8099",
        "/usr/bin/bun",
        lambda argv: calls.append(list(argv)),
    )

    assert len(calls) == len(pages), (
        f"expected one run per page, got {len(calls)} for {len(pages)} pages"
    )
    assert [argv[-1].rsplit("/weaver/", 1)[1] for argv in calls] == [
        "",
        "install/",
        "commands/act/",
    ], f"each page should be captured once, in order; got {calls!r}"


def test_a_failing_capture_stops_the_run_rather_than_reporting_success() -> None:
    """A tool that exits non-zero must not leave a partial snapshot passing.

    Raising is half of it. The other half is stopping: a loop that swallowed
    the first failure and carried on would produce a directory missing one
    page, which compares clean against a baseline that has it.
    """
    attempted: list[str] = []

    def explode(argv: cabc.Sequence[str]) -> None:
        attempted.append(argv[-1])
        raise subprocess.CalledProcessError(1, list(argv))

    with pytest.raises(subprocess.CalledProcessError):
        tools._capture_pages(
            ["", "install/"], Path("/out"), "http://x", "/usr/bin/bun", explode
        )

    assert len(attempted) == 1, (
        f"the run should stop at the first failure, but it attempted "
        f"{len(attempted)} pages: {attempted}"
    )


def test_shots_closes_its_session_even_when_a_page_fails() -> None:
    """An interrupted run must not strand a daemon holding the viewport."""
    calls: list[list[str]] = []

    def fail_on_screenshot(argv: cabc.Sequence[str]) -> None:
        calls.append(list(argv))
        if "screenshot" in argv:
            raise subprocess.CalledProcessError(1, list(argv))

    with pytest.raises(subprocess.CalledProcessError):
        tools._shoot_pages(
            [""], Path("/out"), "http://x", "/usr/bin/agent-browser", fail_on_screenshot
        )

    assert calls[-1][1] == "close", (
        f"the session should be closed on the way out; last call was {calls[-1]!r}"
    )


def test_a_failure_to_close_the_session_does_not_mask_the_real_error() -> None:
    """The page failure is what the reader needs, not the cleanup's complaint."""

    def fail_everything(argv: cabc.Sequence[str]) -> None:
        raise subprocess.CalledProcessError(2, list(argv))

    with pytest.raises(subprocess.CalledProcessError) as caught:
        tools._shoot_pages(
            [""], Path("/out"), "http://x", "/usr/bin/agent-browser", fail_everything
        )

    assert "close" not in caught.value.cmd, (
        f"the surfaced error should be the page's, not the cleanup's; got "
        f"{caught.value.cmd!r}"
    )


def test_every_page_is_shot_at_every_width() -> None:
    """A width that quietly captured nothing would look like a clean run."""
    calls: list[list[str]] = []
    tools._shoot_pages(
        ["", "install/"],
        Path("/out"),
        "http://x",
        "/usr/bin/agent-browser",
        lambda argv: calls.append(list(argv)),
    )

    shots = [argv[2] for argv in calls if argv[1] == "screenshot"]
    out_dir = Path("/out")
    expected = [
        str(out_dir / f"{slug}@{width}.png")
        for width in tools.SCREENSHOT_WIDTHS
        for slug in (paths._slug(""), paths._slug("install/"))
    ]
    assert shots == expected, f"expected {expected!r}, got {shots!r}"


def test_a_missing_tool_names_itself_rather_than_failing_obscurely() -> None:
    """`FileNotFoundError` from deep inside subprocess helps nobody."""
    with pytest.raises(SystemExit) as caught:
        tools._tool("definitely-not-a-real-tool-name")
    assert "definitely-not-a-real-tool-name" in str(caught.value.code), (
        f"the message should name the missing tool; got {caught.value.code!r}"
    )
