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

import hashlib
import json
import os
import re
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
from tests.support.stilyagi_browser import normalize_style
from tests.support.weaver_harness import load

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from syrupy.assertion import SnapshotAssertion

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_NETSUKE = REPO_ROOT / "public" / SITE

tools = load("weaver_snapshot_tools")
document = load("weaver_snapshot_document")

# One docs page that carries each of the shapes the migration had to pin: a
# faux window inside a section (the phone-width full-bleed block), a table
# (the base-layer cell padding), the mobile toggle (a button's pointer), and
# the narrow-screen docs dropdown (an option's padding).
COMPONENT_PAGE = "docs/manifest-reference/"
COMPONENT_SELECTORS = (
    "main.hm-docs-content",
    "section .hm-faux-window",
    "section .hm-faux-window__titlebar",
    "table td",
    "#navbar-mobile-toggle",
    "select option",
    '#navbar a[href="/netsuke/docs/"]',
)

# The properties worth pinning: paint, typography, and the box edges the
# component rules set. Geometry is left out, since it moves with fonts.
STYLE_PROBE = """(() => {
  const keys = ["display", "cursor", "color", "backgroundColor", "fontSize",
    "lineHeight", "fontFamily", "paddingTop", "paddingRight", "paddingBottom",
    "paddingLeft", "marginLeft", "marginRight", "borderTopWidth",
    "borderTopStyle", "borderTopColor", "borderTopLeftRadius", "boxShadow",
    "overflowWrap"];
  const out = {};
  for (const selector of __SELECTORS__) {
    const el = document.querySelector(selector);
    if (!el) { out[selector] = null; continue; }
    const style = getComputedStyle(el);
    out[selector] = Object.fromEntries(keys.map((k) => [k, style[k]]));
  }
  // The base layer describes an element before any class touches it, so it
  // is read off fresh, unclassed elements rather than the page's own, which
  // carry utilities of their own.
  const table = document.createElement("table");
  table.innerHTML = "<tr><td>x</td></tr>";
  const button = document.createElement("button");
  const select = document.createElement("select");
  select.innerHTML = "<option>x</option>";
  document.body.append(table, button, select);
  const cell = getComputedStyle(table.querySelector("td"));
  const option = getComputedStyle(select.querySelector("option"));
  out["__base__"] = {
    cellPadding: [cell.paddingTop, cell.paddingRight,
      cell.paddingBottom, cell.paddingLeft],
    buttonCursor: getComputedStyle(button).cursor,
    optionPadding: [option.paddingTop, option.paddingRight,
      option.paddingBottom, option.paddingLeft],
  };
  table.remove(); button.remove(); select.remove();
  return JSON.stringify(out);
})()""".replace("__SELECTORS__", json.dumps(list(COMPONENT_SELECTORS)))

# Every element in the fixture; a budget small enough to cut the walk short; and
# the laid-out width the fixture gives its paragraph.
WALKER_FIXTURE_ELEMENTS = 10
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


def _walker_with_defaults(drive: cabc.Callable[..., str], expression: str) -> str:
    """Measure the user-agent defaults on a blank page and fill them in.

    The capture does this once per run before the first page opens; the
    fixture page is opened afterwards, so the walk appends nothing to it.
    """
    drive("open", "about:blank")
    return tools._with_defaults(expression, drive("eval", tools._read_defaults_probe()))


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
    # Both walks are prepared before the fixture opens: the defaults are
    # measured on a blank page, and the fixture is then only read.
    source = tools._read_walker()
    walker = _walker_with_defaults(drive, tools._walker_expression(source))
    capped_walker = _walker_with_defaults(
        drive, tools._walker_expression(source, max_nodes=WALKER_BUDGET)
    )
    drive("open", fixture.as_uri())
    result = _evaluate(drive, walker)
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
        "html, head, meta, title, style, body, and the four in the body make "
        "ten elements, and the walk appends none of its own; it counted "
        f"{document['payload']['meta']['visited']}"
    )

    capped = _evaluate(drive, capped_walker)
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


# The two viewports the committed baseline is taken at: the capture's own
# desktop default, which the migration was proved at, and the phone width the
# narrow media queries show at.
BASELINE_VIEWPORTS = {
    "desktop": (tools.CAPTURE_WIDTH, tools.CAPTURE_HEIGHT),
    "phone": (MOBILE_WIDTH, MOBILE_HEIGHT),
}
BASELINE = REPO_ROOT / "tests" / "support" / "netsuke_baseline.json"
UPDATE_BASELINE = "NETSUKE_BASELINE_UPDATE"

# The one thing on a page that changes from build to build without the page
# changing: the forthcoming pages stamp the build date into a heading.
BUILD_DATE = re.compile(r"Status on \d{1,2} [A-Z][a-z]+ \d{4}")


@pytest.fixture(scope="module", params=sorted(BASELINE_VIEWPORTS))
def captured(
    request: pytest.FixtureRequest,
    built_site: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[str, Path]:
    """Run ``capture --site netsuke`` once per viewport, as an operator would.

    ``--site`` selects the tree and the page list, ``--width`` and
    ``--height`` size the viewport; the settle wait and the walker run inside
    agent-browser. Everything between the command line and the JSON on disk
    is exercised as one, and the snapshots serve both the command's own test
    and the baseline comparison.
    """
    del built_site  # the fixture is the build; the tree it returns is Weaver's
    uv_exe = shutil.which("uv") or pytest.skip("uv is not on PATH")
    name = request.param
    width, height = BASELINE_VIEWPORTS[name]
    out_dir = tmp_path_factory.mktemp(f"capture-{name}") / "snapshots"
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
            str(width),
            "--height",
            str(height),
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
    return name, out_dir


@pytest.mark.timeout(900)
def test_the_capture_command_snapshots_every_netsuke_page(
    captured: tuple[str, Path],
) -> None:
    """The command writes one snapshot per page that says how it was taken."""
    name, out_dir = captured
    width, height = BASELINE_VIEWPORTS[name]
    written = sorted(out_dir.glob("*.json"))
    assert len(written) == len(PAGES), (
        f"expected one snapshot per Netsuke page ({len(PAGES)}), got "
        f"{[path.name for path in written]}"
    )
    for snapshot in written:
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
        assert payload["meta"]["viewport"] == {"width": width, "height": height}, (
            f"{snapshot.name} was not laid out at the viewport asked for: "
            f"{payload['meta']['viewport']}"
        )
        assert payload["meta"]["tool"] == "agent-browser", (
            f"{snapshot.name} was not taken by the settled capture path"
        )
        assert payload["payload"]["tree"]["children"], (
            f"{snapshot.name} carries no rendered tree"
        )
        assert payload["payload"]["tree"]["bbox"]["width"] <= width, (
            f"{snapshot.name}'s document is wider than the viewport"
        )


def _digest(snapshot: Path) -> str:
    """Hash a snapshot's normalized tree, with the build date redacted."""
    rendered = BUILD_DATE.sub(
        "Status on <build date>", document._normalized_tree(snapshot)
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


@pytest.mark.timeout(900)
def test_every_page_renders_as_the_committed_baseline(
    captured: tuple[str, Path],
) -> None:
    """Every Netsuke page, at both widths, renders as the committed record says.

    The migration was proved by a diff against the Play CDN rendering, which
    no longer exists in the tree. This is that proof's standing successor: a
    digest of each page's normalized computed-style tree — the same
    normalization ``diff`` compares with — committed in
    ``tests/support/netsuke_baseline.json``. A page that renders differently
    fails here by name; ``scripts/weaver_snapshot.py capture`` and ``diff``
    then show what moved, and once the change is meant, running this test
    with ``NETSUKE_BASELINE_UPDATE=1`` rewrites the record for the commit
    that makes it. The build date the forthcoming pages stamp into a heading
    is the one accepted difference, and it is redacted before hashing.
    """
    name, out_dir = captured
    digests = {path.stem: _digest(path) for path in sorted(out_dir.glob("*.json"))}
    recorded = (
        json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.is_file() else {}
    )
    if os.environ.get(UPDATE_BASELINE):
        recorded[name] = digests
        BASELINE.write_text(
            json.dumps(recorded, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        pytest.skip(
            f"{BASELINE.name} rewritten for {name}; rerun without {UPDATE_BASELINE}"
        )
    expected = recorded.get(name, {})
    changed = sorted(slug for slug in digests if digests[slug] != expected.get(slug))
    missing = sorted(set(expected) - set(digests))
    differing = changed or missing
    assert not differing, (
        f"at {name} width these pages no longer render as the committed baseline "
        f"records: {differing}. Capture with `scripts/weaver_snapshot.py "
        f"capture --site netsuke --width {BASELINE_VIEWPORTS[name][0]} --height "
        f"{BASELINE_VIEWPORTS[name][1]} <out-dir>` at the last good commit and at "
        f"this one and `diff` them; if the change is meant, rerun this test with "
        f"{UPDATE_BASELINE}=1 to record it."
    )


@pytest.fixture(scope="module")
def component_styles(
    drive: cabc.Callable[..., str], served: str
) -> dict[str, dict[str, typ.Any]]:
    """Probe the representative components at a phone width and a desktop one."""
    probed = {}
    for name, width, height in (
        ("phone", MOBILE_WIDTH, MOBILE_HEIGHT),
        ("desktop", DESKTOP_WIDTH, DESKTOP_HEIGHT),
    ):
        _open(drive, served, COMPONENT_PAGE, width, height)
        probed[name] = _evaluate(drive, STYLE_PROBE)
    return probed


@pytest.mark.timeout(300)
@pytest.mark.parametrize("viewport", ["phone", "desktop"])
@pytest.mark.parametrize("selector", COMPONENT_SELECTORS)
def test_component_paint_matches_the_snapshot(
    component_styles: dict[str, dict[str, typ.Any]],
    snapshot: SnapshotAssertion,
    viewport: str,
    selector: str,
) -> None:
    """Each representative component's paint and edges, pinned as a snapshot.

    The migration's proof was a diff against the Play CDN rendering, which
    no longer exists in the tree. This is what stands in for it from here: a
    committed record of what the compiled stylesheet renders for the
    components the migration had to pin by hand, at a phone width and a
    desktop one, so a change to any of them is a change someone chose.
    """
    element = component_styles[viewport][selector]
    assert element is not None, f"{selector} is not on {COMPONENT_PAGE}"
    assert normalize_style(element) == snapshot


@pytest.mark.timeout(300)
def test_the_base_layer_restores_what_v3_preflight_left_alone(
    component_styles: dict[str, dict[str, typ.Any]],
) -> None:
    """`site-base.css` pins three element defaults v4's preflight changed.

    Read off fresh, unclassed elements: the base layer describes an element
    before any class touches it, and the page's own cells and buttons carry
    utilities that would say something else.
    """
    base = component_styles["desktop"]["__base__"]
    assert base["cellPadding"] == ["1px", "1px", "1px", "1px"], (
        f"a cell keeps the user agent's 1px padding; got {base['cellPadding']}"
    )
    assert base["buttonCursor"] == "pointer", (
        "a button shows the pointer, as under v3's preflight; got "
        f"{base['buttonCursor']}"
    )
    assert base["optionPadding"] == ["0px", "2px", "1px", "2px"], (
        f"an option keeps the user agent's padding; got {base['optionPadding']}"
    )


@pytest.mark.timeout(300)
def test_code_panels_run_edge_to_edge_on_a_phone(
    component_styles: dict[str, dict[str, typ.Any]],
) -> None:
    """Below 460px the full-bleed block beats the panel's own utilities."""
    phone = component_styles["phone"]
    main, window, titlebar = (
        phone["main.hm-docs-content"],
        phone["section .hm-faux-window"],
        phone["section .hm-faux-window__titlebar"],
    )
    assert main is not None and window is not None and titlebar is not None, (  # noqa: PT018 - one guard for the three probes
        "the manifest page carries the docs column and a faux window"
    )
    assert (main["paddingLeft"], main["paddingRight"]) == ("0px", "0px"), (
        f"the docs column drops its side padding on a phone; got {main!r}"
    )
    assert main["overflowWrap"] == "break-word", "long tokens wrap rather than overflow"
    assert window["borderTopWidth"] == "0px", "the panel loses its border"
    assert window["borderTopLeftRadius"] == "0px", "and its rounded corner"
    assert window["boxShadow"] == "none", "and its shadow"
    assert (window["marginLeft"], window["marginRight"]) == ("-16px", "-16px"), (
        f"the panel bleeds through the section's 1rem inset; got {window!r}"
    )
    assert titlebar["borderTopLeftRadius"] == "0px", "the titlebar squares off too"

    desktop = component_styles["desktop"]["section .hm-faux-window"]
    assert desktop is not None, "the window is on the desktop page too"
    assert desktop["borderTopLeftRadius"] != "0px", (
        "in the column the panel keeps its rounded corner"
    )


@pytest.mark.timeout(900)
def test_the_shots_command_screenshots_the_netsuke_site_at_three_widths(
    built_site: Path, tmp_path: Path
) -> None:
    """Run ``shots --site netsuke`` as an operator would.

    ``shots`` serves the tree, settles each page, and screenshots it at the
    three fixed widths. The command line is the contract, so it is run as
    one and the images checked for what a reader would open.
    """
    del built_site  # the fixture is the build; the tree it returns is Weaver's
    uv_exe = shutil.which("uv") or pytest.skip("uv is not on PATH")
    out_dir = tmp_path / "shots"
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            uv_exe,
            "run",
            "python",
            "scripts/weaver_snapshot.py",
            "shots",
            "--site",
            SITE,
            str(out_dir),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    assert completed.returncode == 0, (
        f"shots exited {completed.returncode}: {completed.stderr[-2000:]}"
    )
    written = sorted(out_dir.glob("*.png"))
    assert len(written) == len(PAGES) * len(tools.SCREENSHOT_WIDTHS), (
        f"expected one image per page per width, got {len(written)}"
    )
    for image in written:
        header = image.read_bytes()[:8]
        assert header == b"\x89PNG\r\n\x1a\n", f"{image.name} is not a PNG"
        assert image.stat().st_size > 1024, f"{image.name} is too small to be a page"  # noqa: PLR2004 - a blank PNG is far smaller
