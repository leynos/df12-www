"""Driving the external tools, and the argv each command hands them.

The argv builders are pure, so what a command would run can be asserted
without a browser; `Runner` is the seam the commands take their process
launcher through, for the same reason.
"""

from __future__ import annotations

import collections.abc as cabc
import contextlib
import os
import shutil
import subprocess
import typing as typ

from weaver_snapshot_paths import REPO_ROOT, _slug

if typ.TYPE_CHECKING:
    from pathlib import Path

# 360 exercises the mobile drawer, 768 the tablet breakpoint, and 1440 the
# fixed-sidebar layout the site was designed against.
SCREENSHOT_WIDTHS = (360, 768, 1440)

# The walker mode's node budget. The largest Weaver page is well under this;
# the ceiling only guards against a runaway capture.
MAX_NODES = 8000

# How long a browser-driving subprocess may take before the run is called off.
# A headless browser that never returns would otherwise hang the snapshot
# indefinitely. Matches the timeout the css-view and Playwright probes in
# tests/ already use for the same tools.
TOOL_TIMEOUT_SECONDS = 90


def _tool(name: str) -> str:
    """Resolve an external tool to an absolute path.

    Parameters
    ----------
    name
        The executable's name, as it appears on ``PATH``.

    Returns
    -------
    str
        The absolute path to the executable.

    Raises
    ------
    SystemExit
        If the tool is not on ``PATH``, with a message naming it.
    """
    found = shutil.which(name)
    if found is None:
        message = f"{name} is not on PATH"
        raise SystemExit(message)
    return found


# What a command needs from the outside world to drive a tool. Injecting it
# rather than calling `subprocess.run` inline is what lets the argv a command
# builds be asserted without a browser, a server, or a filesystem.
type Runner = cabc.Callable[[cabc.Sequence[str]], None]


def _run_tool(argv: cabc.Sequence[str]) -> None:
    """Run an external tool to completion, or raise.

    Parameters
    ----------
    argv
        The command to run, already resolved to an absolute executable.

    Raises
    ------
    subprocess.CalledProcessError
        If the tool exits non-zero.
    subprocess.TimeoutExpired
        If it has not finished within :data:`TOOL_TIMEOUT_SECONDS`. A headless
        browser that never returns would otherwise hang the run indefinitely.
    """
    subprocess.run(  # noqa: S603 - fixed argv built from the published tree
        list(argv),
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
        timeout=TOOL_TIMEOUT_SECONDS,
    )


def _session_name() -> str:
    """Name the browser session this process should drive.

    A dedicated session keeps the run clear of any interactive browsing. It
    also has to be unique per process: ``agent-browser`` sessions are named
    globally and hold one viewport and one current page between calls, so two
    concurrent runs sharing a name would interleave — one resizing the
    viewport while the other screenshots, producing images at a width neither
    asked for and reporting success for both.

    Returns
    -------
    str
        A session name unique to this process.
    """
    return f"weaver-shots-{os.getpid()}"


def _css_view_argv(bun: str, base: str, page: str, out_dir: Path) -> list[str]:
    """Build the ``css-view`` command that snapshots one page.

    Parameters
    ----------
    bun
        Absolute path to the ``bun`` executable.
    base
        The origin the local server is listening on, without a trailing slash.
    page
        A page path relative to ``/weaver/``, as :func:`_page_paths` returns.
    out_dir
        Directory the JSON snapshot is written into.

    Returns
    -------
    list of str
        The full argv. The browser is pinned rather than left to css-view's
        default, so a change to that default cannot swap the engine — and the
        rendering — out from under a comparison.
    """
    return [
        bun,
        "x",
        "css-view",
        "--mode",
        "walker",
        "--browser",
        "chromium",
        "--max-nodes",
        str(MAX_NODES),
        "--wait-until",
        "networkidle",
        "--output",
        str(out_dir / f"{_slug(page)}.json"),
        f"{base}/weaver/{page}",
    ]


def _screenshot_argv(path: Path) -> list[str]:
    """Build the ``agent-browser`` arguments that capture one full-page image.

    Parameters
    ----------
    path
        Absolute path to write the PNG to.

    Returns
    -------
    list of str
        The subcommand and its arguments, without the executable or session.
        The path is positional and must precede the flags: passing ``--full``
        first makes agent-browser read the path as a selector and write the
        image elsewhere, reporting success either way. agent-browser also runs
        as a daemon with its own working directory, so the path must be
        absolute.
    """
    return ["screenshot", str(path), "--full"]


def _capture_pages(
    pages: cabc.Sequence[str],
    out_dir: Path,
    base: str,
    bun: str,
    run: Runner,
) -> None:
    """Snapshot each page in turn, reporting progress as it goes.

    Parameters
    ----------
    pages
        Page paths relative to ``/weaver/``.
    out_dir
        Directory to write one JSON snapshot per page into.
    base
        The origin the local server is listening on.
    bun
        Absolute path to the ``bun`` executable.
    run
        How to run a tool. Injected so a test can assert the argv without
        launching a browser.
    """
    for page in pages:
        run(_css_view_argv(bun, base, page, out_dir))
        print(f"  {_slug(page)}")


def _shoot_pages(
    pages: cabc.Sequence[str],
    out_dir: Path,
    base: str,
    browser: str,
    run: Runner,
) -> None:
    """Screenshot each page at each width, closing the session afterwards.

    The session is closed in a ``finally`` so an interrupted run does not
    strand a browser daemon holding the viewport it last set.

    Parameters
    ----------
    pages
        Page paths relative to ``/weaver/``.
    out_dir
        Directory to write the PNG files into.
    base
        The origin the local server is listening on.
    browser
        Absolute path to the ``agent-browser`` executable.
    run
        How to run a tool. Injected so a test can assert the argv without
        launching a browser.
    """
    session = ["--session", _session_name()]

    def drive(*args: str) -> None:
        run([browser, *args, *session])

    try:
        for width in SCREENSHOT_WIDTHS:
            drive("set", "viewport", str(width), "900")
            for page in pages:
                drive("open", f"{base}/weaver/{page}")
                drive(*_screenshot_argv(out_dir / f"{_slug(page)}@{width}.png"))
            print(f"  {width}px done")
    finally:
        with contextlib.suppress(
            subprocess.CalledProcessError, subprocess.TimeoutExpired
        ):
            drive("close")
