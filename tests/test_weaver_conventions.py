"""Conventions the Weaver markup and the build have to keep.

Two utilities of the same kind on one element make the winner a source-order
accident, and a build step that writes into a directory the dev watcher
watches makes the watcher rebuild in response to its own output. Neither shows
up as a failure anywhere else.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_WEAVER = REPO_ROOT / "public" / "weaver"
WEAVER_TEMPLATES = REPO_ROOT / "templates" / "weaver"
WEAVER_STYLES = REPO_ROOT / "src" / "styles"
COMPILED_STYLESHEET = PUBLIC_WEAVER / "assets" / "styles" / "weaver.css"


# A Tailwind font-size utility, as a whole class token. Anchored at both ends
# so `text-base-content` is not read as `text-base`, which is the mistake that
# makes a naive search of this markup report duplicates that are not there.
FONT_SIZE = re.compile(r"^text-(?:[3-9]xs|2xs|xs|sm|base|lg|xl|[2-9]xl)$")


# Both quote forms. `templates/weaver/_icons.jinja` is single-quoted, so a
# double-quote-only pattern skips it entirely — and it is generated, which is
# exactly the kind of file nobody would notice going unchecked.
CLASS_ATTRIBUTE = re.compile(r"""class\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.DOTALL)


# Directories `bun run dev` watches, from the `dev` script in `package.json`.
# A build step that writes into one of these makes the watcher rebuild in
# response to its own output.
WATCHED_ROOTS = ("src", "df12_pages", "config", "scripts")


def test_no_element_declares_two_font_sizes_at_once() -> None:
    """Two font-size utilities on one element make the winner a source-order accident.

    The Sempai page carried `text-xs ... text-3xs` on one contents link for
    several commits: the later class won, so that one link rendered smaller
    than its eight siblings and nothing said why. Commit `16dd6ae1` resolved it
    by dropping `text-3xs`, since `text-xs` is what the other eight carry.

    Only unprefixed utilities are counted. A responsive variant beside a base
    size — `text-sm md:text-base` — is the intended way to change size at a
    breakpoint, not a duplicate.
    """
    offenders: dict[str, list[str]] = {}
    for source in sorted(WEAVER_TEMPLATES.rglob("*.jinja")):
        # Matched against the whole file rather than line by line: a `class`
        # attribute long enough to be wrapped would otherwise be seen as two
        # fragments, neither of which is an attribute, and a duplicate split
        # across the wrap would go unreported. The line number comes from the
        # match offset, and the offset keys the report, so two attributes on
        # one line are both kept.
        text = source.read_text(encoding="utf-8")
        for attribute in CLASS_ATTRIBUTE.finditer(text):
            value = attribute.group(1) or attribute.group(2) or ""
            sizes = [token for token in value.split() if FONT_SIZE.match(token)]
            if len(sizes) > 1:
                number = text.count("\n", 0, attribute.start()) + 1
                where = f"{source.relative_to(REPO_ROOT)}:{number}+{attribute.start()}"
                offenders[where] = sizes

    assert not offenders, (
        "these elements declare more than one font size, so which one applies "
        f"depends on the order the utilities happen to be written in: {offenders}"
    )


@pytest.mark.parametrize(
    ("markup", "expected"),
    [
        pytest.param(
            '<div class="text-xs text-3xs">',
            ["text-xs", "text-3xs"],
            id="double-quoted-duplicate",
        ),
        pytest.param(
            "<div class='text-xs text-3xs'>",
            ["text-xs", "text-3xs"],
            id="single-quoted-duplicate",
        ),
        pytest.param(
            '<div class="text-sm md:text-base lg:text-lg">',
            ["text-sm"],
            id="double-quoted-responsive",
        ),
        pytest.param(
            "<div class='text-sm md:text-base lg:text-lg'>",
            ["text-sm"],
            id="single-quoted-responsive",
        ),
        pytest.param(
            '<div class="text-xs text-base-content/82">',
            ["text-xs"],
            id="a-colour-token-is-not-a-size",
        ),
        pytest.param('<div class="font-mono">', [], id="no-size-at-all"),
    ],
)
def test_the_scan_reads_class_attributes_in_either_quote_form(
    markup: str, expected: list[str]
) -> None:
    """A double-quote-only pattern skipped `_icons.jinja`, which is single-quoted.

    The value is captured by one group or the other depending on which quote
    the attribute used, so both have to be consulted; taking only the first
    would read a single-quoted attribute as empty and report no sizes at all.
    """
    found = [
        token
        for attribute in CLASS_ATTRIBUTE.finditer(markup)
        for token in (attribute.group(1) or attribute.group(2) or "").split()
        if FONT_SIZE.match(token)
    ]
    assert found == expected, f"expected {expected} in {markup!r}, found {found}"


@pytest.mark.parametrize(
    ("classes", "expected"),
    [
        # The reason the pattern is anchored: a colour token that starts with
        # a size's name is not a size.
        ("text-xs text-base-content/82", 1),
        ("block pl-4 text-xs text-base-content/82 hover:text-accent-ink", 1),
        ("text-xs text-3xs", 2),
        # A breakpoint variant is how a size is meant to change, not a clash.
        ("text-sm md:text-base lg:text-lg", 1),
        ("font-mono tracking-stamp", 0),
    ],
)
def test_the_font_size_pattern_counts_whole_tokens(classes: str, expected: int) -> None:
    """The check is only as good as its ability to tell a size from a colour."""
    sizes = [token for token in classes.split() if FONT_SIZE.match(token)]
    assert len(sizes) == expected, (
        f"expected {expected} font-size utilities in {classes!r}, found {sizes}"
    )


def _dev_watch_ignores() -> list[str]:
    """Return the ignore patterns the dev watcher is invoked with."""
    package = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    return re.findall(r"-i '([^']+)'", package["scripts"]["dev"])


@pytest.mark.timeout(600)
def test_a_build_does_not_rewrite_anything_the_dev_watcher_watches(
    built_site: Path,
) -> None:
    """`make dev` rebuilds on any change under `src/`, so a build must settle.

    The Episodic search index is generated into
    `src/static/episodic/assets/search/`, which `bun run dev` watches. While
    the build rewrote it unconditionally the watcher rebuilt in response to its
    own output, and kept doing so: ten full builds in five minutes with nobody
    touching the tree.

    This runs the build a second time over an already-built tree and asserts
    nothing under a watched root moved. It is the invariant that keeps the
    watcher quiet, and it holds for any build step, not just that one.
    """
    assert built_site.is_dir(), "the session fixture should have built the tree"

    def snapshot() -> dict[Path, tuple[int, float]]:
        seen: dict[Path, tuple[int, float]] = {}
        for root in WATCHED_ROOTS:
            for path in sorted((REPO_ROOT / root).rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    stats = path.stat()
                    seen[path] = (stats.st_size, stats.st_mtime)
        return seen

    # `or pytest.skip(...)` rather than an `if`, because the skip's `NoReturn`
    # is what narrows this to `str` for the call below.
    bun_exe = shutil.which("bun") or pytest.skip("bun is not on PATH")

    before = snapshot()
    subprocess.run([bun_exe, "run", "build"], cwd=REPO_ROOT, check=True)  # noqa: S603 - fixed argv, no user input
    after = snapshot()

    touched = sorted(
        str(path.relative_to(REPO_ROOT))
        for path in set(before) | set(after)
        if before.get(path) != after.get(path)
    )
    assert not touched, (
        "a second build rewrote files the dev watcher is watching, so "
        "`bun run dev` rebuilds in response to its own output and never "
        f"settles: {touched}"
    )


def test_the_dev_watcher_also_ignores_the_generated_search_index() -> None:
    """A second guard, in case a build step ever writes unconditionally again.

    The build not rewriting its own inputs is the real fix; this is the belt to
    its braces, and cheap. If the ignore is removed the watcher is one careless
    write away from looping again.
    """
    ignores = _dev_watch_ignores()

    assert any("episodic/assets/search" in pattern for pattern in ignores), (
        "the dev watcher should ignore the generated Episodic search index; "
        f"its ignore patterns are {ignores}"
    )
