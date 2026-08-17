"""Capture and compare computed-style snapshots of the Weaver sub-site.

The Weaver sub-site is being migrated from the Tailwind Play CDN to the
repository's compiled Tailwind v4 and daisyUI v5 pipeline. The migration is
meant to be behaviour-preserving, so each step is judged by diffing a fresh
snapshot against a baseline taken before any edit. See
``docs/execplans/weaver-daisy-migration.md``.

Three subcommands, each safe to re-run:

    uv run python scripts/weaver_snapshot.py capture .weaver-baseline
    uv run python scripts/weaver_snapshot.py shots .weaver-baseline-shots
    uv run python scripts/weaver_snapshot.py diff .weaver-baseline .weaver-after

``capture`` records computed styles via ``css-view`` and is the objective
gate; ``diff`` exits non-zero when any page changed. ``shots`` records
full-page screenshots via ``agent-browser`` for human review, because some
regressions — a wrong icon glyph, a texture that failed to load — are obvious
to the eye and invisible in a style diff.

All three read the published tree under ``public/``, so run ``bun run build``
first. Each serves that tree itself on a local port and stops the server
afterwards, including on failure.
"""

from __future__ import annotations

import contextlib
import difflib
import json
import shutil
import subprocess
import sys
import time
import typing as typ
import urllib.error
import urllib.request
from pathlib import Path

import cyclopts

if typ.TYPE_CHECKING:
    import collections.abc as cabc

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_WEAVER = REPO_ROOT / "public" / "weaver"
HTTP_SERVER = REPO_ROOT / "node_modules" / ".bin" / "http-server"

# 360 exercises the mobile drawer, 768 the tablet breakpoint, and 1440 the
# fixed-sidebar layout the site was designed against.
SCREENSHOT_WIDTHS = (360, 768, 1440)

# The walker mode's node budget. The largest Weaver page is well under this;
# the ceiling only guards against a runaway capture.
MAX_NODES = 8000

app = cyclopts.App(
    name="weaver-snapshot",
    help="Capture and compare Weaver computed-style snapshots.",
)


def _page_paths() -> list[str]:
    """List the published Weaver pages as base-relative URL paths.

    Derived from the published tree rather than hard-coded, so a page added to
    ``config/pages.yaml`` is captured without editing this script.

    Returns
    -------
    list of str
        Paths relative to ``/weaver/``, such as ``""`` for the home page and
        ``"commands/act/"`` for a nested one, in sorted order.
    """
    if not PUBLIC_WEAVER.is_dir():
        message = "public/weaver is missing; run 'bun run build' first"
        raise SystemExit(message)
    pages = [
        f"{path.parent.relative_to(PUBLIC_WEAVER).as_posix()}/".removeprefix("./")
        for path in PUBLIC_WEAVER.rglob("index.html")
    ]
    return sorted(page if page != "./" else "" for page in pages)


def _slug(page: str) -> str:
    """Turn a page path into a filename stem.

    Parameters
    ----------
    page
        A path relative to ``/weaver/``, such as ``"commands/act/"``.

    Returns
    -------
    str
        A flat, filesystem-safe stem: ``"home"`` for the home page and
        ``"commands__act"`` for the example above.
    """
    return page.strip("/").replace("/", "__") or "home"


@contextlib.contextmanager
def _served(port: int) -> cabc.Iterator[str]:
    """Serve ``public/`` locally for the duration of the context.

    Parameters
    ----------
    port
        TCP port to listen on.

    Yields
    ------
    str
        The base URL of the running server, without a trailing slash.

    Raises
    ------
    SystemExit
        If the server does not accept connections within roughly ten seconds.
    """
    if not HTTP_SERVER.is_file():
        message = "node_modules/.bin/http-server is missing; run 'bun install'"
        raise SystemExit(message)

    base = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(  # noqa: S603 - fixed argv, no shell, no user input
        [str(HTTP_SERVER), "public", "-p", str(port), "-c-1", "--silent"],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # Poll rather than sleeping a fixed interval, so a slow start does not
        # silently yield a directory full of failed captures.
        for _ in range(50):
            try:
                with urllib.request.urlopen(f"{base}/weaver/", timeout=1):  # noqa: S310 - literal loopback URL
                    break
            except (urllib.error.URLError, OSError):
                time.sleep(0.2)
        else:
            message = f"http-server did not come up on port {port}"
            raise SystemExit(message)
        yield base
    finally:
        server.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            server.wait(timeout=10)


def _prepare_output_dir(out_dir: Path, suffix: str) -> Path:
    """Create the output directory and clear any previous run's files.

    Parameters
    ----------
    out_dir
        Directory to create. Created with parents if absent.
    suffix
        File extension to clear, including the leading dot.

    Returns
    -------
    Path
        The resolved absolute path to the directory.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob(f"*{suffix}"):
        stale.unlink()
    return out_dir.resolve()


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


@app.command
def capture(out_dir: Path, /, *, port: int = 8099) -> None:
    """Record a computed-style snapshot of every Weaver page.

    Parameters
    ----------
    out_dir
        Directory to write one JSON snapshot per page into. Existing snapshots
        are replaced.
    port
        Port to serve ``public/`` on.
    """
    resolved = _prepare_output_dir(out_dir, ".json")
    pages = _page_paths()
    bun = _tool("bun")
    print(f"capturing {len(pages)} Weaver pages into {resolved}")

    with _served(port) as base:
        for page in pages:
            slug = _slug(page)
            subprocess.run(  # noqa: S603 - fixed argv built from the published tree
                [
                    bun,
                    "x",
                    "css-view",
                    "--mode",
                    "walker",
                    # Pinned rather than left to css-view's default, so a
                    # change to that default cannot swap the engine — and the
                    # rendering — out from under a comparison.
                    "--browser",
                    "chromium",
                    "--max-nodes",
                    str(MAX_NODES),
                    "--wait-until",
                    "networkidle",
                    "--output",
                    str(resolved / f"{slug}.json"),
                    f"{base}/weaver/{page}",
                ],
                cwd=REPO_ROOT,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            print(f"  {slug}")

    print(f"done: {resolved}")


@app.command
def shots(out_dir: Path, /, *, port: int = 8098) -> None:
    """Record full-page screenshots of every Weaver page at three widths.

    Parameters
    ----------
    out_dir
        Directory to write PNG files into. Existing images are replaced.
    port
        Port to serve ``public/`` on.
    """
    browser = _tool("agent-browser")
    resolved = _prepare_output_dir(out_dir, ".png")
    pages = _page_paths()
    widths = " ".join(str(width) for width in SCREENSHOT_WIDTHS)
    print(f"screenshotting {len(pages)} Weaver pages at {widths} into {resolved}")

    # A dedicated session keeps this clear of any interactive browsing.
    env_session = ["--session", "weaver-shots"]

    def run(*args: str) -> None:
        subprocess.run(  # noqa: S603 - fixed argv built from the published tree
            [browser, *args, *env_session],
            cwd=REPO_ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )

    with _served(port) as base:
        try:
            for width in SCREENSHOT_WIDTHS:
                run("set", "viewport", str(width), "900")
                for page in pages:
                    run("open", f"{base}/weaver/{page}")
                    # The path is positional and must precede the flags:
                    # passing --full first makes agent-browser read the path as
                    # a selector and write the image elsewhere, reporting
                    # success either way. It also runs as a daemon with its own
                    # working directory, so the path must be absolute.
                    run(
                        "screenshot",
                        str(resolved / f"{_slug(page)}@{width}.png"),
                        "--full",
                    )
                print(f"  {width}px done")
        finally:
            with contextlib.suppress(subprocess.CalledProcessError):
                run("close")

    print(f"done: {resolved}")


def _normalize(node: dict[str, typ.Any]) -> dict[str, typ.Any]:
    """Strip incidental variation from one walker node, recursively.

    Two properties vary between captures of an unchanged page:

    - ``opacity`` on a node running a CSS animation. The Weaver pages carry an
      ``animate-pulse`` status dot whose opacity is sampled mid-cycle.
    - Bounding-box coordinates, which carry subpixel text-shaping jitter.
      Rounding to two decimal places absorbs that without hiding a real
      layout shift.

    Parameters
    ----------
    node
        A walker-mode node, as emitted by ``css-view``.

    Returns
    -------
    dict
        The node with those variations removed, and its children likewise.
    """
    style = dict(node.get("styleDiff") or {})
    if style.get("animation-name", "none") != "none":
        style.pop("opacity", None)

    bbox = node.get("bbox")
    if isinstance(bbox, dict):
        bbox = {
            key: round(value, 2) if isinstance(value, (int, float)) else value
            for key, value in bbox.items()
        }

    normalized = dict(node)
    normalized["styleDiff"] = style
    if bbox is not None:
        normalized["bbox"] = bbox
    normalized["children"] = [_normalize(child) for child in node.get("children") or []]
    return normalized


def _normalized_tree(snapshot: Path) -> str:
    """Read a snapshot and render its tree as stable, comparable text.

    Parameters
    ----------
    snapshot
        Path to a ``css-view`` JSON snapshot.

    Returns
    -------
    str
        Pretty-printed JSON with sorted keys, ready to hand to a line differ.
        The capture envelope — URL, timestamp, browser — is dropped, since it
        records when the snapshot was taken, not what the page looks like.
    """
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    tree = _normalize(payload["payload"]["tree"])
    return json.dumps(tree, indent=2, sort_keys=True, ensure_ascii=False)


@app.command
def diff(before: Path, after: Path, /, *, context: int = 60) -> None:
    """Compare two snapshot directories and report per-page differences.

    Parameters
    ----------
    before
        Directory holding the baseline snapshots.
    after
        Directory holding the snapshots to check.
    context
        Maximum number of diff lines to print per differing page.

    Raises
    ------
    SystemExit
        With status 1 when any page differs, so this can gate a milestone.
    """
    baseline = sorted(before.glob("*.json"))
    if not baseline:
        message = f"no snapshots in {before}"
        raise SystemExit(message)

    differing = 0
    for snapshot in baseline:
        name = snapshot.stem
        candidate = after / snapshot.name
        if not candidate.is_file():
            print(f"{name:<24} MISSING in {after}")
            differing += 1
            continue

        lines = list(
            difflib.unified_diff(
                _normalized_tree(snapshot).splitlines(),
                _normalized_tree(candidate).splitlines(),
                fromfile=str(snapshot),
                tofile=str(candidate),
                lineterm="",
            )
        )
        if not lines:
            print(f"{name:<24} no differences")
            continue

        changed = sum(1 for line in lines[2:] if line[:1] in {"+", "-"})
        print(f"{name:<24} DIFFERS ({changed} changed lines)")
        for line in lines[:context]:
            print(f"    {line}")
        differing += 1

    # A page present only in the after directory is a new page, which is as
    # much a change as an altered one.
    for candidate in sorted(after.glob("*.json")):
        if not (before / candidate.name).is_file():
            print(f"{candidate.stem:<24} NEW in {after}")
            differing += 1

    print(f"{len(baseline)} pages compared, {differing} differing.")
    if differing:
        sys.exit(1)


if __name__ == "__main__":
    app()
