"""Driving the external tools, and the argv each command hands them.

The argv builders are pure, so what a command would run can be asserted
without a browser; `Runner` is the seam the commands take their process
launcher through, for the same reason.
"""

from __future__ import annotations

import collections.abc as cabc
import contextlib
import json
import os
import shutil
import subprocess
import typing as typ

from weaver_snapshot_paths import DEFAULT_SITE, REPO_ROOT, _slug

if typ.TYPE_CHECKING:
    from pathlib import Path

# 360 exercises the mobile drawer, 768 the tablet breakpoint, and 1440 the
# fixed-sidebar layout the site was designed against.
SCREENSHOT_WIDTHS = (360, 768, 1440)

# The walker mode's node budget. The largest Weaver page is well under this;
# the ceiling only guards against a runaway capture.
MAX_NODES = 8000

# How many times one page is captured while icons on it are still unrendered.
#
# Netsuke draws its icons with Iconify, a script that fetches each glyph from
# a CDN after the page loads and swaps the placeholder `<span class="iconify">`
# for an `<svg>`. css-view waits for the network to go idle, but Iconify's
# request can start after that moment, so a capture sometimes lands with a
# page's icons still unrendered — and a missing icon is not a style change but
# a layout one, moving every line below it. Three pages carry an icon the set
# does not have at all, so a span can also remain for good; the capture with
# the fewest unrendered icons is kept, which is the steady state either way.
ICON_ATTEMPTS = 3


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


def _session_name(site: str = DEFAULT_SITE) -> str:
    """Name the browser session this process should drive.

    A dedicated session keeps the run clear of any interactive browsing. It
    also has to be unique per process: ``agent-browser`` sessions are named
    globally and hold one viewport and one current page between calls, so two
    concurrent runs sharing a name would interleave — one resizing the
    viewport while the other screenshots, producing images at a width neither
    asked for and reporting success for both.

    Parameters
    ----------
    site
        The sub-site being screenshotted, so the name says what the session
        is for.

    Returns
    -------
    str
        A session name unique to this process.
    """
    return f"{site}-shots-{os.getpid()}"


def _css_view_argv(
    bun: str, base: str, page: str, out_dir: Path, site: str = DEFAULT_SITE
) -> list[str]:
    """Build the ``css-view`` command that snapshots one page.

    Parameters
    ----------
    bun
        Absolute path to the ``bun`` executable.
    base
        The origin the local server is listening on, without a trailing slash.
    page
        A page path relative to the sub-site's base path, as
        :func:`_page_paths` returns.
    out_dir
        Directory the JSON snapshot is written into.
    site
        The sub-site the page belongs to; the first segment of its URL.

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
        f"{base}/{site}/{page}",
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


def _unrendered_icons(snapshot: Path) -> int:
    """Count the Iconify placeholders a captured page still carries.

    Parameters
    ----------
    snapshot
        A walker-mode snapshot css-view has just written.

    Returns
    -------
    int
        How many ``<span class="iconify">`` nodes the tree holds. Once Iconify
        has rendered an icon the span is an ``<svg>``, whose classes the
        walker reports as an ``SVGAnimatedString`` rather than by name, so
        only the unrendered ones count. A snapshot that cannot be read counts
        as settled: the diff will name a page that is missing or malformed,
        and repeating the capture would not help it.
    """
    try:
        tree = json.loads(snapshot.read_text(encoding="utf-8"))["payload"]["tree"]
    except (OSError, ValueError, KeyError, TypeError):
        return 0

    def count(node: typ.Any) -> int:  # noqa: ANN401 - the document is untyped upstream data
        if not isinstance(node, cabc.Mapping):
            return 0
        classes = node.get("classes")
        own = int(
            node.get("tag") == "span"
            and isinstance(classes, list)
            and "iconify" in classes
        )
        children = node.get("children")
        if not isinstance(children, list):
            return own
        return own + sum(count(child) for child in children)

    return count(tree)


def _capture_pages(  # noqa: PLR0913 - one seam per outward dependency
    pages: cabc.Sequence[str],
    out_dir: Path,
    base: str,
    bun: str,
    run: Runner,
    site: str = DEFAULT_SITE,
    unrendered: cabc.Callable[[Path], int] = _unrendered_icons,
) -> None:
    """Snapshot each page in turn, reporting progress as it goes.

    A page whose icons had not rendered when the walker ran is captured
    again, up to :data:`ICON_ATTEMPTS` times, and the attempt with the fewest
    unrendered icons is the one kept.

    Parameters
    ----------
    pages
        Page paths relative to the sub-site's base path.
    out_dir
        Directory to write one JSON snapshot per page into.
    base
        The origin the local server is listening on.
    bun
        Absolute path to the ``bun`` executable.
    run
        How to run a tool. Injected so a test can assert the argv without
        launching a browser.
    site
        The sub-site the pages belong to.
    unrendered
        How many icons a written snapshot still shows unrendered. Injected so
        the retry can be exercised without a browser.
    """
    for page in pages:
        _capture_settled(page, out_dir, base, bun, run, site, unrendered)


def _capture_settled(  # noqa: PLR0913 - one seam per outward dependency
    page: str,
    out_dir: Path,
    base: str,
    bun: str,
    run: Runner,
    site: str,
    unrendered: cabc.Callable[[Path], int],
) -> None:
    """Capture one page until its icons have rendered, or the attempts run out.

    Parameters
    ----------
    page
        The page path relative to the sub-site's base path.
    out_dir
        Directory the snapshot is written into.
    base
        The origin the local server is listening on.
    bun
        Absolute path to the ``bun`` executable.
    run
        How to run a tool.
    site
        The sub-site the page belongs to.
    unrendered
        How many icons a written snapshot still shows unrendered.
    """
    argv = _css_view_argv(bun, base, page, out_dir, site)
    output = out_dir / f"{_slug(page)}.json"
    best_remaining: int | None = None
    best_text = ""
    for _attempt in range(ICON_ATTEMPTS):
        run(argv)
        remaining = unrendered(output)
        if remaining == 0:
            print(f"  {_slug(page)}")
            return
        if best_remaining is None or remaining < best_remaining:
            best_remaining, best_text = remaining, output.read_text(encoding="utf-8")
    # Every attempt left something unrendered. The last attempt is what is on
    # disk; the best one is what the comparison should see.
    output.write_text(best_text, encoding="utf-8")
    print(
        f"  {_slug(page)} ({best_remaining} unrendered icons after "
        f"{ICON_ATTEMPTS} attempts)"
    )


def _shoot_pages(  # noqa: PLR0913 - one seam per outward dependency
    pages: cabc.Sequence[str],
    out_dir: Path,
    base: str,
    browser: str,
    run: Runner,
    site: str = DEFAULT_SITE,
) -> None:
    """Screenshot each page at each width, closing the session afterwards.

    The session is closed in a ``finally`` so an interrupted run does not
    strand a browser daemon holding the viewport it last set.

    Parameters
    ----------
    pages
        Page paths relative to the sub-site's base path.
    out_dir
        Directory to write the PNG files into.
    base
        The origin the local server is listening on.
    browser
        Absolute path to the ``agent-browser`` executable.
    run
        How to run a tool. Injected so a test can assert the argv without
        launching a browser.
    site
        The sub-site the pages belong to.
    """
    session = ["--session", _session_name(site)]

    def drive(*args: str) -> None:
        run([browser, *args, *session])

    try:
        for width in SCREENSHOT_WIDTHS:
            drive("set", "viewport", str(width), "900")
            for page in pages:
                drive("open", f"{base}/{site}/{page}")
                drive(*_screenshot_argv(out_dir / f"{_slug(page)}@{width}.png"))
            print(f"  {width}px done")
    finally:
        with contextlib.suppress(
            subprocess.CalledProcessError, subprocess.TimeoutExpired
        ):
            drive("close")
