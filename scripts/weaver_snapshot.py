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

This module is the command surface. The work sits in siblings named for what
they do, imported the way `scripts/` modules import each other: the harness is
run by path, so its own directory is on `sys.path`.

- ``weaver_snapshot_paths``     — the published tree, page list, and slugs
- ``weaver_snapshot_locking``   — advisory locks and lock-file hygiene
- ``weaver_snapshot_output``    — staging and failure-atomic publication
- ``weaver_snapshot_ownership`` — proving whose server answered
- ``weaver_snapshot_serving``   — ports, the server, and its lifecycle
- ``weaver_snapshot_tools``     — argv for css-view and agent-browser
- ``weaver_snapshot_colour``    — one colour written one way
- ``weaver_snapshot_normalize`` — reducing a tree to what is visible
"""

from __future__ import annotations

import contextlib
import difflib
import sys

# `Path` is annotated on the commands below, and cyclopts resolves those
# annotations at runtime to build the parser. Deferring it behind
# TYPE_CHECKING makes every command fail to register with `NameError: name
# 'Path' is not defined`.
from pathlib import Path  # noqa: TC003

import cyclopts
from weaver_snapshot_locking import _exclusive, _output_lock_path
from weaver_snapshot_normalize import _normalized_tree
from weaver_snapshot_output import _staged
from weaver_snapshot_paths import _page_paths
from weaver_snapshot_serving import _served
from weaver_snapshot_tools import (
    SCREENSHOT_WIDTHS,
    _capture_pages,
    _run_tool,
    _shoot_pages,
    _tool,
)

app = cyclopts.App(
    name="weaver-snapshot",
    help="Capture and compare Weaver computed-style snapshots.",
)


@app.command
def capture(out_dir: Path, /, *, port: int = 0) -> None:
    """Record a computed-style snapshot of every Weaver page.

    Parameters
    ----------
    out_dir
        Directory to write one JSON snapshot per page into. Existing snapshots
        are replaced.
    port
        Port to serve ``public/`` on. The default of ``0`` asks the kernel for
        a free one, so two runs in two worktrees do not contend at all; pass a
        number only to reach the served tree from a browser by hand.
    """
    pages = _page_paths()
    bun = _tool("bun")
    print(f"capturing {len(pages)} Weaver pages into {out_dir}")

    with _staged(out_dir, ".json") as staging, _served(port) as base:
        _capture_pages(pages, staging, base, bun, _run_tool)

    print(f"done: {out_dir.resolve()}")


@app.command
def shots(out_dir: Path, /, *, port: int = 0) -> None:
    """Record full-page screenshots of every Weaver page at three widths.

    Parameters
    ----------
    out_dir
        Directory to write PNG files into. Existing images are replaced.
    port
        Port to serve ``public/`` on. The default of ``0`` asks the kernel for
        a free one, so two runs in two worktrees do not contend at all; pass a
        number only to reach the served tree from a browser by hand.
    """
    browser = _tool("agent-browser")
    pages = _page_paths()
    widths = " ".join(str(width) for width in SCREENSHOT_WIDTHS)
    print(f"screenshotting {len(pages)} Weaver pages at {widths} into {out_dir}")

    with _staged(out_dir, ".png") as staging, _served(port) as base:
        _shoot_pages(pages, staging, base, browser, _run_tool)

    print(f"done: {out_dir.resolve()}")


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
    # Read both directories under the same lock publication takes, so a diff
    # can never observe one of them halfway through being replaced. Without
    # this the reader is the remaining hole in the ownership protocol: the
    # writer's per-file replacements are each atomic, but the sequence of them
    # is not, and a diff that started midway would compare some pages from
    # this run against some from the last and report the difference as the
    # branch's work.
    with contextlib.ExitStack() as reading:
        for directory in _reading_order(before, after):
            reading.enter_context(
                _exclusive(_output_lock_path(directory), f"{directory}")
            )
        _diff_locked(before, after, context)


def _reading_order(before: Path, after: Path) -> list[Path]:
    """Order two output directories so two readers cannot deadlock on them.

    Taking them in a consistent order — resolved, then sorted — means two runs
    reading the same pair take them the same way round rather than each
    holding what the other wants. A directory named twice is locked once.

    Parameters
    ----------
    before
        The baseline directory.
    after
        The directory being checked.

    Returns
    -------
    list of Path
        The distinct resolved directories, in a stable order.
    """
    return sorted({before.resolve(), after.resolve()})


def _diff_locked(before: Path, after: Path, context: int) -> None:
    """Compare two snapshot directories, with both already locked for reading.

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
        With status 1 when any page differs.
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
