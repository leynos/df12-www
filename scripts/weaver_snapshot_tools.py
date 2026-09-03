"""Driving agent-browser, and the argv each command hands it.

Both commands drive the same browser session the same way: size the
viewport, open the page, wait for the network to go idle and then for the
page to say it has settled, and only then take the capture — a computed-style
walk for ``capture``, a full-page image for ``shots``.

The argv builders are pure, so what a command would run can be asserted
without a browser; `Runner` and `Reader` are the seams the commands take
their process launcher through, for the same reason.
"""

from __future__ import annotations

import collections.abc as cabc
import contextlib
import datetime as dt
import json
import os
import shutil
import subprocess
import typing as typ
from pathlib import Path

from weaver_snapshot_paths import DEFAULT_SITE, REPO_ROOT, _slug

# 360 exercises the mobile drawer, 768 the tablet breakpoint, and 1440 the
# fixed-sidebar layout the site was designed against.
SCREENSHOT_WIDTHS = (360, 768, 1440)

# The walker's node budget. The largest page is well under this; the ceiling
# only guards against a runaway capture.
MAX_NODES = 8000

# How much of each element's text the walker keeps. Enough to tell two
# elements apart in a diff, not enough to reproduce the page.
TEXT_CLIP = 80

# The viewport every capture is taken at. css-view's Playwright default, which
# the first baselines were taken against; agent-browser's own default is not
# the same height, and `min-h-screen` would otherwise move.
CAPTURE_WIDTH, CAPTURE_HEIGHT = 1280, 720

# The properties the walker compares against the parent rather than the
# user-agent default — css-view's DEFAULT_INHERITED_PROPERTIES, which every
# baseline was taken with.
INHERITED_PROPERTIES = (
    "color",
    "font",
    "font-family",
    "font-size",
    "font-style",
    "font-weight",
    "font-stretch",
    "font-variant",
    "font-feature-settings",
    "font-kerning",
    "line-height",
    "letter-spacing",
    "word-spacing",
    "text-align",
    "text-indent",
    "text-transform",
    "text-decoration-color",
    "text-decoration-line",
    "text-decoration-style",
    "white-space",
    "visibility",
    "cursor",
    "direction",
    "unicode-bidi",
    "list-style-type",
    "list-style-position",
    "list-style-image",
    "quotes",
)

# The properties the walker reports on every node whatever they equal. A
# margin equal to the user-agent default — a paragraph's 16px below — would
# otherwise be left out, and the normalizer folds margins into the gaps
# between siblings, which needs every margin.
ALWAYS_PROPERTIES = ("margin-top", "margin-right", "margin-bottom", "margin-left")

# The walker evaluator, read once per run. See the file's own header.
WALKER = Path(__file__).with_name("weaver_snapshot_walker.js")

# What "the page has settled" means, as an expression `agent-browser wait
# --fn` polls until it is truthy.
#
# Netsuke draws its icons with Iconify, a script that fetches each glyph from
# a CDN after the page loads and swaps the placeholder `<span class="iconify">`
# for an `<svg>` — and it asks for them a moment *after* the network has gone
# idle, so a capture taken at network-idle catches the placeholders, which is a
# layout change rather than a style one. The expression asks Iconify itself to
# say when every icon on the page has either arrived or been reported missing,
# and then waits for the arrived ones to be drawn. A page without Iconify is
# settled as soon as it is asked. State is parked on `window` so the poll can
# ask the same question repeatedly and register the callback only once.
SETTLED = """(() => {
  const spans = () => [...document.querySelectorAll('span.iconify[data-icon]')];
  if (!window.Iconify) return true;
  if (window.__snapshotSettle === undefined) {
    const state = { done: false, missing: new Set() };
    window.__snapshotSettle = state;
    const names = [...new Set(spans().map((s) => s.dataset.icon))];
    if (!names.length) {
      state.done = true;
    } else {
      Iconify.loadIcons(names, (_loaded, missing, pending) => {
        if (pending.length) return;
        for (const icon of missing) state.missing.add(`${icon.prefix}:${icon.name}`);
        state.done = true;
      });
    }
  }
  const state = window.__snapshotSettle;
  return state.done && spans().every((s) => state.missing.has(s.dataset.icon));
})()"""

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


# The same, for a tool whose standard output is the result — `agent-browser
# eval`, which prints what the expression returned.
type Reader = cabc.Callable[[cabc.Sequence[str]], str]


def _read_tool(argv: cabc.Sequence[str]) -> str:
    """Run an external tool to completion and return what it printed.

    Parameters
    ----------
    argv
        The command to run, already resolved to an absolute executable.

    Returns
    -------
    str
        The tool's standard output.

    Raises
    ------
    subprocess.CalledProcessError
        If the tool exits non-zero.
    subprocess.TimeoutExpired
        If it has not finished within :data:`TOOL_TIMEOUT_SECONDS`.
    """
    completed = subprocess.run(  # noqa: S603 - fixed argv built from the published tree
        list(argv),
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=TOOL_TIMEOUT_SECONDS,
    )
    return completed.stdout


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


def _session_name(site: str = DEFAULT_SITE, purpose: str = "shots") -> str:
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
        The sub-site being captured, so the name says what the session is
        for.
    purpose
        ``shots`` or ``capture``, for the same reason.

    Returns
    -------
    str
        A session name unique to this process.
    """
    return f"{site}-{purpose}-{os.getpid()}"


def _walker_expression(max_nodes: int = MAX_NODES, text_clip: int = TEXT_CLIP) -> str:
    """Read the walker evaluator and fill in its parameters.

    Parameters
    ----------
    max_nodes
        How many elements the walk may visit before it stops.
    text_clip
        How many characters of each element's text to keep.

    Returns
    -------
    str
        A JavaScript expression that evaluates to the snapshot as a JSON
        string, ready for ``agent-browser eval``.
    """
    return (
        WALKER.read_text(encoding="utf-8")
        .replace("__INHERITED__", json.dumps(list(INHERITED_PROPERTIES)))
        .replace("__ALWAYS__", json.dumps(list(ALWAYS_PROPERTIES)))
        .replace("__MAX_NODES__", str(max_nodes))
        .replace("__TEXT_CLIP__", str(text_clip))
    )


def _snapshot_document(url: str, evaluated: str) -> dict[str, typ.Any]:
    """Wrap what the walker returned in the envelope css-view writes.

    Parameters
    ----------
    url
        The page the walk was taken over.
    evaluated
        What ``agent-browser eval`` printed: the walker's JSON string, itself
        JSON-encoded once more by the tool.

    Returns
    -------
    dict
        A document with ``payload.tree`` where every reader of a snapshot
        expects it, and a ``meta`` recording when and how it was taken.
    """
    result = json.loads(evaluated.strip())
    if isinstance(result, str):
        result = json.loads(result)
    return {
        "meta": {
            "url": url,
            "capturedAt": dt.datetime.now(dt.UTC).isoformat(),
            "mode": "walker",
            "tool": "agent-browser",
            "viewport": {"width": CAPTURE_WIDTH, "height": CAPTURE_HEIGHT},
        },
        "payload": {
            "tree": result["tree"],
            "meta": {
                "visited": result["visited"],
                "maxNodes": MAX_NODES,
                "textClip": TEXT_CLIP,
            },
        },
    }


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
        A walker-mode snapshot the harness has just written.

    Returns
    -------
    int
        How many ``<span class="iconify">`` nodes the tree holds. Once Iconify
        has rendered an icon the span is an ``<svg>``, whose classes the
        walker reports as an ``SVGAnimatedString`` rather than by name, so
        only the unrendered ones count. After the settle wait these are the
        icons the set does not have, and the count is reported so a page
        whose icons never arrived can be told from one that has none.
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


def _open_settled(drive: cabc.Callable[..., None], url: str) -> bool:
    """Load a page and wait until it has settled.

    Parameters
    ----------
    drive
        Runs one ``agent-browser`` subcommand in the session.
    url
        The page to open.

    Returns
    -------
    bool
        Whether the page settled within the tool's timeout. One that did not
        is captured anyway — a page that never settles is still a page — and
        the caller says so beside its name.
    """
    drive("open", url)
    drive("wait", "--load", "networkidle")
    try:
        drive("wait", "--fn", SETTLED)
    except subprocess.CalledProcessError:
        return False
    return True


def _capture_pages(  # noqa: PLR0913 - one seam per outward dependency
    pages: cabc.Sequence[str],
    out_dir: Path,
    base: str,
    browser: str,
    run: Runner,
    read: Reader,
    site: str = DEFAULT_SITE,
) -> None:
    """Snapshot each page in turn, reporting progress as it goes.

    The session is closed in a ``finally`` so an interrupted run does not
    strand a browser daemon holding the viewport it last set.

    Parameters
    ----------
    pages
        Page paths relative to the sub-site's base path.
    out_dir
        Directory to write one JSON snapshot per page into.
    base
        The origin the local server is listening on.
    browser
        Absolute path to the ``agent-browser`` executable.
    run
        How to run a tool whose output is not wanted. Injected so a test can
        assert the argv without launching a browser.
    read
        How to run a tool and keep what it printed. The walker's result comes
        back this way.
    site
        The sub-site the pages belong to.
    """
    session = ["--session", _session_name(site, "capture")]

    def drive(*args: str) -> None:
        run([browser, *args, *session])

    walker = _walker_expression()
    try:
        drive("set", "viewport", str(CAPTURE_WIDTH), str(CAPTURE_HEIGHT))
        for page in pages:
            url = f"{base}/{site}/{page}"
            settled = _open_settled(drive, url)
            document = _snapshot_document(
                url, read([browser, "eval", walker, *session])
            )
            output = out_dir / f"{_slug(page)}.json"
            output.write_text(json.dumps(document), encoding="utf-8")
            notes = []
            if not settled:
                notes.append("did not settle")
            if remaining := _unrendered_icons(output):
                notes.append(f"{remaining} icons the set does not have")
            print(f"  {_slug(page)}" + (f" ({'; '.join(notes)})" if notes else ""))
    finally:
        with contextlib.suppress(
            subprocess.CalledProcessError, subprocess.TimeoutExpired
        ):
            drive("close")


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
                _open_settled(drive, f"{base}/{site}/{page}")
                drive(*_screenshot_argv(out_dir / f"{_slug(page)}@{width}.png"))
            print(f"  {width}px done")
    finally:
        with contextlib.suppress(
            subprocess.CalledProcessError, subprocess.TimeoutExpired
        ):
            drive("close")
