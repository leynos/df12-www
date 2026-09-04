"""What every published Netsuke page does when a browser loads it.

The chrome's two layouts — the link list at desktop widths and the drawer
below the tablet breakpoint — and whether the document fits the viewport it
was given. These are the properties the daisyUI migration must not disturb,
and they are asserted from the browser because a computed-style diff cannot
tell whether a page that laid out wider than 360px did so before as well.

Marked ``playwright``, so `-m "not playwright"` deselects the lot while
iterating on something else.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import typing as typ
from pathlib import Path

import pytest

from tests.support.netsuke_browser import (
    BASE_PATH,
    DESKTOP_HEIGHT,
    DESKTOP_WIDTH,
    KNOWN_OVERFLOW,
    LAYOUT,
    MOBILE_HEIGHT,
    MOBILE_WIDTH,
    PAGES,
    SITE,
    STANDALONE,
    _evaluate,
    _open,
)
from tests.support.weaver_harness import load

if typ.TYPE_CHECKING:
    import collections.abc as cabc

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_NETSUKE = REPO_ROOT / "public" / SITE

tools = load("weaver_snapshot_tools")

# Every element in the fixture, plus the iframe the walker adds to read
# user-agent defaults from; a budget small enough to cut the walk short; and
# the laid-out width the fixture gives its paragraph.
WALKER_FIXTURE_ELEMENTS = 11
WALKER_BUDGET = 3
CHILD_WIDTH = 120

# A document small enough to reason about by hand, with one of everything the
# walker has to get right: an inherited property set on the parent and left
# alone on the child, a non-inherited one the child sets for itself, a margin
# equal to the user-agent default, a hidden element, an input with a value,
# and text long enough to clip.
WALKER_FIXTURE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>walker</title>
<style>
  body { margin: 0; }
  #parent { color: rgb(1, 2, 3); }
  #child { background-color: rgb(4, 5, 6); width: __WIDTH__px; height: 40px; }
  #hidden { display: none; }
</style></head>
<body>
  <div id="parent" class="  a   b  ">
    <p id="child" role="note">__TEXT__</p>
    <span id="hidden">gone</span>
    <input id="field" name="q" value="typed">
  </div>
</body></html>
""".replace("__WIDTH__", str(CHILD_WIDTH)).replace("__TEXT__", "x" * 200)

pytestmark = pytest.mark.playwright


@pytest.mark.timeout(900)
@pytest.mark.parametrize("page", PAGES)
def test_a_netsuke_page_fits_a_phone(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """At 360 the toggle is the navigation and the link list is hidden.

    Getting that backwards leaves a page with no way to navigate at all. A
    page wider than the viewport is the other classic mobile failure: the code
    panels scroll on purpose and are allowed to, but the document is not.

    Four pages already overflow at this width and are waived by name; the
    waiver asserts the overflow is still there, so fixing one of them fails
    this test until the entry is removed, and worsening one fails it outright.
    """
    _open(drive, served, page, MOBILE_WIDTH, MOBILE_HEIGHT)
    narrow = _evaluate(drive, LAYOUT)

    if page not in STANDALONE:
        assert narrow["toggle"], (
            f"{BASE_PATH}{page} has no drawer toggle at {MOBILE_WIDTH}px, so the "
            "menu it hides cannot be opened"
        )
        assert not narrow["nav"], (
            f"{BASE_PATH}{page} still lays out the desktop link list at "
            f"{MOBILE_WIDTH}px, where it does not fit"
        )
    if (known := KNOWN_OVERFLOW.get(page)) is not None:
        assert narrow["viewport"] < narrow["page"] <= known, (
            f"{BASE_PATH}{page} was waived at {known}px wide but now lays out at "
            f"{narrow['page']}px; if it fits, drop it from KNOWN_OVERFLOW, and "
            "if it grew, that is a regression"
        )
        return
    assert narrow["page"] <= narrow["viewport"], (
        f"{BASE_PATH}{page} lays out {narrow['page']}px wide in a "
        f"{narrow['viewport']}px viewport, so the whole page scrolls sideways"
    )


@pytest.mark.timeout(900)
@pytest.mark.parametrize("page", PAGES)
def test_a_netsuke_page_lays_out_its_nav_on_a_desktop(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """The wide layout's half of the swap: the link list, and no toggle."""
    _open(drive, served, page, DESKTOP_WIDTH, DESKTOP_HEIGHT)
    wide = _evaluate(drive, LAYOUT)

    if page not in STANDALONE:
        assert wide["nav"], f"{BASE_PATH}{page} has no link list at {DESKTOP_WIDTH}px"
        assert not wide["toggle"], (
            f"{BASE_PATH}{page} shows the drawer toggle at {DESKTOP_WIDTH}px, "
            "beside the link list it stands in for"
        )
    assert wide["page"] <= wide["viewport"], (
        f"{BASE_PATH}{page} lays out {wide['page']}px wide in a "
        f"{wide['viewport']}px viewport"
    )


def test_the_published_tree_holds_exactly_the_netsuke_pages_checked_here(
    built_site: Path,
) -> None:
    """The page list is taken from the config, so it can drift from the build.

    Parametrization happens at collection, before anything is built, which is
    why the list cannot simply be read off the published tree. A page
    generated but not listed here would go unchecked, and one listed but not
    generated would make every other test fail on a 404.
    """
    del built_site  # the fixture is the build; the tree it returns is Weaver's
    published = sorted(
        f"{path.parent.relative_to(PUBLIC_NETSUKE).as_posix()}/".removeprefix("./")
        for path in PUBLIC_NETSUKE.rglob("index.html")
    )
    assert published == sorted(PAGES), (
        "config/pages.yaml and the published tree disagree about which Netsuke "
        f"pages exist. Published: {published}. Checked here: {sorted(PAGES)}"
    )


@pytest.mark.timeout(300)
def test_the_walker_reports_what_the_capture_relies_on(
    drive: cabc.Callable[..., str], tmp_path: Path
) -> None:
    """Run the vendored walker over a document small enough to check by hand.

    The harness trusts the walker for four things a snapshot diff then
    depends on: a property is written only where it differs from what the
    element would have had anyway, the always-reported properties are written
    whatever they equal, each node carries the metadata the normalization
    keys on, and the walk stops at the node budget. The walker is JavaScript
    evaluated inside the page, so the only oracle is a browser.
    """
    fixture = tmp_path / "walker.html"
    fixture.write_text(WALKER_FIXTURE, encoding="utf-8")
    drive("set", "viewport", "800", "600")
    drive("open", fixture.as_uri())
    result = _evaluate(drive, tools._walker_expression())
    document = tools._snapshot_document(fixture.as_uri(), json.dumps(result))
    tree = document["payload"]["tree"]

    by_id: dict[str, dict[str, typ.Any]] = {}

    def index(node: dict[str, typ.Any]) -> None:
        if node.get("id"):
            by_id[node["id"]] = node
        for child in node["children"]:
            index(child)

    index(tree)
    parent, child, hidden, field = (
        by_id[key] for key in ("parent", "child", "hidden", "field")
    )

    assert tree["tag"] == "html", "the walk starts at the document element"
    assert parent["classes"] == ["a", "b"], (
        f"classes are split on whitespace and trimmed; got {parent['classes']!r}"
    )
    assert parent["styleDiff"]["color"] == "rgb(1, 2, 3)", (
        "a colour set on an element differs from its parent and is reported"
    )
    assert "color" not in child["styleDiff"], (
        "an inherited property equal to the parent's is not a difference; "
        f"got {child['styleDiff']!r}"
    )
    assert child["styleDiff"]["background-color"] == "rgb(4, 5, 6)", (
        "a non-inherited property set on the element is reported"
    )
    assert "background-color" not in parent["styleDiff"], (
        "a non-inherited property at its user-agent default is not reported"
    )
    assert child["styleDiff"]["margin-bottom"] == "16px", (
        "a margin is always reported, even at the paragraph's default; got "
        f"{child['styleDiff'].get('margin-bottom')!r}"
    )
    assert child["role"] == "note", "the role attribute reaches the node"
    assert child["text"] == "x" * tools.TEXT_CLIP, (
        f"text is clipped to {tools.TEXT_CLIP} characters"
    )
    assert child["bbox"]["width"] == CHILD_WIDTH, (
        f"the bounding box is the laid-out one; got {child['bbox']!r}"
    )
    assert hidden["styleDiff"]["display"] == "none", "display: none is reported"
    assert hidden["bbox"]["width"] == 0, "a hidden element has no box"
    assert field["name"] == "q", "the name attribute reaches the node"
    assert field["text"] == "typed", "an input reports its value as its text"
    assert document["payload"]["meta"]["visited"] == WALKER_FIXTURE_ELEMENTS, (
        "html, head, meta, title, style, body, the four in the body, and the "
        "walker's own iframe make eleven elements; the walk counted "
        f"{document['payload']['meta']['visited']}"
    )

    capped = _evaluate(drive, tools._walker_expression(max_nodes=WALKER_BUDGET))
    capped_document = tools._snapshot_document(fixture.as_uri(), json.dumps(capped))

    def count(node: dict[str, typ.Any]) -> int:
        return 1 + sum(count(child) for child in node["children"])

    assert count(capped_document["payload"]["tree"]) == WALKER_BUDGET, (
        "the walk keeps no more nodes than its budget"
    )
    assert capped_document["payload"]["meta"]["visited"] > WALKER_BUDGET, (
        "a walk that overran its budget says so in the visit count, which is "
        "how a reader tells a clipped snapshot from a small page"
    )


@pytest.mark.timeout(900)
def test_the_capture_command_snapshots_the_netsuke_site_at_a_phone_width(
    built_site: Path, tmp_path: Path
) -> None:
    """Run ``capture`` as an operator would, with every new option set.

    ``--site`` selects the tree and the page list, ``--width`` and
    ``--height`` size the viewport; the settle wait and the walker run inside
    agent-browser. Everything between the command line and the JSON on disk
    is exercised here as one, and the snapshots must say how they were taken.
    """
    del built_site  # the fixture is the build; the tree it returns is Weaver's
    uv_exe = shutil.which("uv") or pytest.skip("uv is not on PATH")
    out_dir = tmp_path / "snapshots"
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            uv_exe,
            "run",
            "python",
            "scripts/weaver_snapshot.py",
            "capture",
            "--site",
            SITE,
            "--width",
            str(MOBILE_WIDTH),
            "--height",
            str(MOBILE_HEIGHT),
            str(out_dir),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    assert completed.returncode == 0, (
        f"capture exited {completed.returncode}: {completed.stderr[-2000:]}"
    )

    written = sorted(out_dir.glob("*.json"))
    assert len(written) == len(PAGES), (
        f"expected one snapshot per Netsuke page ({len(PAGES)}), got "
        f"{[path.name for path in written]}"
    )
    for snapshot in written:
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
        assert payload["meta"]["viewport"] == {
            "width": MOBILE_WIDTH,
            "height": MOBILE_HEIGHT,
        }, (
            f"{snapshot.name} was not laid out at the viewport asked for: "
            f"{payload['meta']['viewport']}"
        )
        assert payload["meta"]["tool"] == "agent-browser", (
            f"{snapshot.name} was not taken by the settled capture path"
        )
        assert payload["payload"]["tree"]["children"], (
            f"{snapshot.name} carries no rendered tree"
        )
        assert payload["payload"]["tree"]["bbox"]["width"] <= MOBILE_WIDTH, (
            f"{snapshot.name}'s document is wider than the phone viewport"
        )
