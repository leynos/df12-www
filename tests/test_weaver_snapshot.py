"""Tests for the Weaver computed-style snapshot harness.

The harness in ``scripts/weaver_snapshot.py`` is what the Tailwind v4 and
daisyUI v5 migration is judged by, so its normalization has to be right in
both directions. Too little and every translucent colour on the site reports
as changed, burying the handful that really did; too much and a genuine
regression is normalized away and ships.
"""

from __future__ import annotations

import contextlib
import fcntl
import functools
import http.server
import importlib.util
import json
import os
import socket
import subprocess
import threading
import typing as typ
from pathlib import Path

if typ.TYPE_CHECKING:
    import collections.abc as cabc

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Stands in for whatever goes wrong between taking the startup lock and the
# server answering. Named here so the `pytest.raises` block stays one
# statement, which is what makes it assert on that statement alone.
_MID_START_FAILURE = "the port was occupied"

# A port number for the messages these tests read back. Nothing binds it;
# the throwaway servers are given one by the kernel.
PORT = 8099

# The harness is a script rather than a package module, so it is loaded by
# path rather than imported by name.
_SPEC = importlib.util.spec_from_file_location(
    "weaver_snapshot", REPO_ROOT / "scripts" / "weaver_snapshot.py"
)
assert _SPEC is not None, "scripts/weaver_snapshot.py could not be located"
assert _SPEC.loader is not None, (
    "spec for weaver_snapshot has no loader; it cannot be executed"
)
weaver_snapshot = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(weaver_snapshot)


@pytest.mark.parametrize(
    ("notation", "expected"),
    [
        # Tailwind v3 resolved an opacity modifier to rgba(); v4 resolves it
        # through color-mix() in Oklab. These two are the same colour, and the
        # differ has to say so.
        ("rgba(25, 60, 110, 0.8)", "rgba(25, 60, 110, 0.800)"),
        (
            "oklab(0.359209 -0.0202858 -0.0934766 / 0.8)",
            "rgba(25, 60, 110, 0.800)",
        ),
        ("rgb(25, 60, 110)", "rgba(25, 60, 110, 1.000)"),
        ("oklab(0.359209 -0.0202858 -0.0934766)", "rgba(25, 60, 110, 1.000)"),
        # Oklch is the notation the theme itself is written in.
        ("oklch(1 0 0)", "rgba(255, 255, 255, 1.000)"),
        ("oklch(0 0 0)", "rgba(0, 0, 0, 1.000)"),
        # A colour embedded among other components is rewritten in place.
        (
            "2px 2px 0px 0px rgba(25, 60, 110, 1)",
            "2px 2px 0px 0px rgba(25, 60, 110, 1.000)",
        ),
        # Values carrying no colour are left alone.
        ("0px", "0px"),
        ("1px solid", "1px solid"),
    ],
)
def test_colour_notations_canonicalize_to_the_same_rgba(
    notation: str, expected: str
) -> None:
    """Equivalent colours should compare equal whatever notation they wear."""
    assert weaver_snapshot._canonical_value(notation) == expected, (
        f"{notation!r} should canonicalize to {expected!r}, so that two ways "
        f"of writing one colour compare equal; got "
        f"{weaver_snapshot._canonical_value(notation)!r}"
    )


def test_distinct_colours_stay_distinct() -> None:
    """Normalization must not collapse colours that genuinely differ.

    Tailwind v4 redefined its stock palette in OKLCH, so ``green-500`` moved
    from ``#22c55e`` to a slightly different green. That is a real change and
    the differ has to report it.
    """
    v3_green = weaver_snapshot._canonical_value("rgb(34, 197, 94)")
    v4_green = weaver_snapshot._canonical_value("oklch(0.723 0.219 149.579)")
    assert v3_green != v4_green, (
        "Tailwind v4 redefined green-500 in OKLCH, which is a real change to "
        "the page; canonicalizing must not collapse it into the v3 value"
    )


def test_placeholder_shadow_layers_are_dropped() -> None:
    """A shadow that paints nothing should not count as a difference."""
    v3 = (
        "rgba(0, 0, 0, 0) 0px 0px 0px 0px, rgba(0, 0, 0, 0) 0px 0px 0px 0px, "
        "rgba(0, 0, 0, 0.05) 0px 1px 2px 0px"
    )
    v4 = (
        "rgba(0, 0, 0, 0) 0px 0px 0px 0px, rgba(0, 0, 0, 0) 0px 0px 0px 0px, "
        "rgba(0, 0, 0, 0) 0px 0px 0px 0px, rgba(0, 0, 0, 0) 0px 0px 0px 0px, "
        "rgba(0, 0, 0, 0.05) 0px 1px 2px 0px"
    )
    normalize = weaver_snapshot._canonical_shadow
    assert normalize(weaver_snapshot._canonical_value(v3)) == normalize(
        weaver_snapshot._canonical_value(v4)
    ), (
        "v3 and v4 pad a shadow with different numbers of transparent layers; "
        "dropping the layers that paint nothing is what makes the two equal"
    )
    assert normalize(weaver_snapshot._canonical_value(v3)) == (
        "rgba(0, 0, 0, 0.050) 0px 1px 2px 0px"
    ), (
        "only the placeholder layers should go; the one layer that actually "
        "paints must survive intact"
    )


def test_a_real_shadow_change_survives_normalization() -> None:
    """Dropping placeholders must not hide a shadow that actually moved."""
    normalize = weaver_snapshot._canonical_shadow
    two_px = normalize("rgba(25, 60, 110, 1.000) 2px 2px 0px 0px")
    four_px = normalize("rgba(25, 60, 110, 1.000) 4px 4px 0px 0px")
    assert two_px != four_px, (
        "dropping placeholder layers must not also hide a shadow that moved; "
        "2px and 4px offsets are a visible difference"
    )


def _node(**style: str) -> dict[str, typ.Any]:
    """Build a minimal walker node carrying the given computed styles."""
    return {"tag": "div", "classes": [], "styleDiff": dict(style), "children": []}


def test_tailwind_internal_properties_are_ignored() -> None:
    """``--tw-*`` variables are plumbing, not something a reader can see."""
    normalized = weaver_snapshot._normalize(
        _node(**{"--tw-text-opacity": "1", "color": "rgb(1, 2, 3)"})
    )
    assert normalized["styleDiff"] == {"color": "rgba(1, 2, 3, 1.000)"}, (
        "`--tw-*` variables are Tailwind's plumbing and change between "
        f"versions without the page changing; got {normalized['styleDiff']!r}"
    )


def test_animated_opacity_is_ignored_but_static_opacity_is_not() -> None:
    """Only a node mid-animation should have its sampled opacity discarded."""
    animated = weaver_snapshot._normalize(
        _node(**{"animation-name": "pulse", "opacity": "0.694981"})
    )
    assert "opacity" not in animated["styleDiff"], (
        "a node mid-animation reports whatever opacity the sample caught, "
        f"which differs run to run; got {animated['styleDiff']!r}"
    )

    static = weaver_snapshot._normalize(_node(opacity="0.5"))
    assert static["styleDiff"]["opacity"] == "0.5", (
        "a static opacity is a real declaration and must survive; got "
        f"{static['styleDiff']!r}"
    )


def test_normalization_recurses_into_children() -> None:
    """Nested nodes get the same treatment as the root."""
    tree = _node(color="rgb(1, 2, 3)")
    tree["children"] = [_node(**{"--tw-ring-offset-width": "0px"})]
    normalized = weaver_snapshot._normalize(tree)
    assert normalized["children"][0]["styleDiff"] == {}, (
        "normalization has to reach every node, not just the root; the child's "
        f"`--tw-*` property survived as {normalized['children'][0]['styleDiff']!r}"
    )


def test_canonical_style_leaves_its_argument_alone() -> None:
    """The caller's ``styleDiff`` must survive normalization untouched.

    ``_normalize`` shallow-copies each node, so a helper that edited the
    styles in place would reach back into the parsed snapshot and corrupt it
    for anything reading the same object afterwards.
    """
    original = {"--tw-text-opacity": "1", "color": "rgb(1, 2, 3)"}
    style_diff = dict(original)
    normalized = weaver_snapshot._canonical_style(style_diff)

    assert style_diff == original, (
        f"_canonical_style must not modify its argument; it became {style_diff!r}"
    )
    assert normalized == {"color": "rgba(1, 2, 3, 1.000)"}, (
        "the returned styles should drop --tw-* plumbing and canonicalize the "
        f"colour; got {normalized!r}"
    )


def test_canonical_style_treats_an_absent_style_diff_as_empty() -> None:
    """A node with no styles of its own is not an error."""
    assert weaver_snapshot._canonical_style(None) == {}, (
        "a missing styleDiff should normalize to an empty mapping"
    )


def test_resolve_tracked_reports_a_departure_and_carries_it_down() -> None:
    """A tracked property is kept only where the node overrides the parent."""
    style = {"color-scheme": "dark", "caret-color": "rgb(1, 2, 3)"}
    carried = weaver_snapshot._resolve_tracked(
        style, {"color-scheme": "light", "caret-color": "rgb(1, 2, 3)"}
    )

    assert style == {"color-scheme": "dark"}, (
        "the property matching the parent should be dropped and the departure "
        f"kept; the styles came out as {style!r}"
    )
    assert carried == {"color-scheme": "dark", "caret-color": "rgb(1, 2, 3)"}, (
        "children are compared against the overridden value, not the one the "
        f"parent handed down; got {carried!r}"
    )


def test_resolve_tracked_leaves_the_inherited_mapping_alone() -> None:
    """The parent's values are shared down the tree, so they must not be edited."""
    inherited = {"color-scheme": "light"}
    weaver_snapshot._resolve_tracked({"color-scheme": "dark"}, inherited)

    assert inherited == {"color-scheme": "light"}, (
        "_resolve_tracked must return a new mapping rather than mutate the "
        f"one its siblings also hold; it became {inherited!r}"
    )


@pytest.mark.parametrize(
    "bbox",
    [
        None,
        "0 0 640 480",
        [0, 0, 640, 480],
        42,
    ],
    ids=["none", "string", "list", "number"],
)
def test_a_non_mapping_bbox_survives_unchanged(
    bbox: list[typ.Any] | str | float | None,
) -> None:
    """Only a mapping is rounded; anything else passes straight through.

    The walker owns this field's shape. If it ever reports a bbox some other
    way, that belongs in the diff for someone to look at — replacing it with
    ``None``, or dropping it, would hide the very change worth seeing.
    """
    node = _node()
    node["bbox"] = bbox
    normalized = weaver_snapshot._normalize(node)

    assert "bbox" in normalized, (
        f"the bbox key should be preserved for a {type(bbox).__name__} value"
    )
    assert normalized["bbox"] == bbox, (
        f"a non-mapping bbox should pass through unchanged; {bbox!r} became "
        f"{normalized['bbox']!r}"
    )


def test_a_node_without_a_bbox_does_not_gain_one() -> None:
    """Normalization reports what the walker saw, and invents nothing."""
    normalized = weaver_snapshot._normalize(_node())
    assert "bbox" not in normalized, (
        f"a node the walker gave no bbox should not acquire one; got "
        f"{normalized.get('bbox')!r}"
    )


def test_bounding_boxes_are_rounded_not_discarded() -> None:
    """Subpixel jitter is absorbed; a real layout shift still shows."""
    jittered_y = 1850.004
    settled_y = 1850.0
    height = 3700.0
    node = _node()
    node["bbox"] = {"x": 0.0, "y": jittered_y, "width": 640.0, "height": height}
    normalized = weaver_snapshot._normalize(node)
    assert normalized["bbox"]["y"] == settled_y, (
        f"subpixel jitter should round away, or every capture differs from "
        f"the last; {jittered_y} normalized to {normalized['bbox']['y']}"
    )

    # The other half of the docstring's promise, which nothing checked: a
    # rounding that also swallowed real movement would make the whole
    # comparison worthless, and would have passed the assertion above.
    shifted = _node()
    shifted["bbox"] = {"x": 0.0, "y": jittered_y + 1, "width": 640.0, "height": height}
    assert (
        weaver_snapshot._normalize(shifted)["bbox"]["y"] != normalized["bbox"]["y"]
    ), "a one-pixel shift must survive normalization, or diffs mean nothing"
    assert normalized["bbox"]["height"] == height, (
        f"a whole-number dimension should pass through untouched; {height} "
        f"became {normalized['bbox']['height']}"
    )


def test_invisible_border_colours_are_ignored() -> None:
    """A colour on an undrawn border is not something a reader can see."""
    normalized = weaver_snapshot._normalize(
        _node(**{"border-top-color": "rgb(229, 231, 235)"})
    )
    assert normalized["styleDiff"] == {}, (
        "a colour on an edge of zero width paints nothing, so it is not a "
        f"difference a reader could see; got {normalized['styleDiff']!r}"
    )


def test_drawn_border_colours_are_kept() -> None:
    """Give an edge a width and its colour becomes a real difference again."""
    normalized = weaver_snapshot._normalize(
        _node(
            **{
                "border-top-width": "2px",
                "border-top-color": "rgb(229, 231, 235)",
            }
        )
    )
    assert normalized["styleDiff"]["border-top-color"] == (
        "rgba(229, 231, 235, 1.000)"
    ), (
        "the same colour on an edge that is drawn is a real difference and "
        f"must be kept; got {normalized['styleDiff']!r}"
    )


def test_a_logical_border_width_keeps_its_physical_colour() -> None:
    """The physical and logical spellings name the same edge."""
    normalized = weaver_snapshot._normalize(
        _node(
            **{
                "border-block-start-width": "1px",
                "border-top-color": "rgb(1, 2, 3)",
            }
        )
    )
    assert "border-top-color" in normalized["styleDiff"], (
        "`border-block-start-width` draws the same edge as `border-top-width`, "
        f"so its colour is visible too; got {normalized['styleDiff']!r}"
    )


def test_root_only_declarations_are_not_repeated_down_the_tree() -> None:
    """One declaration on the root should be reported once, not per node.

    The walker compares ``color-scheme`` against the user-agent default rather
    than against the parent, so a single ``:root`` rule shows up on every node
    beneath it.
    """
    root = _node(**{"color-scheme": "light"})
    child = _node(**{"color-scheme": "light"})
    grandchild = _node(**{"color-scheme": "dark"})
    child["children"] = [grandchild]
    root["children"] = [child]

    normalized = weaver_snapshot._normalize(root)
    assert normalized["styleDiff"] == {"color-scheme": "light"}, (
        f"the node that declares it should report it; got {normalized['styleDiff']!r}"
    )
    assert normalized["children"][0]["styleDiff"] == {}, (
        "a child inheriting the root's value is not declaring anything, and "
        "reporting it on every node buries the ones that differ; got "
        f"{normalized['children'][0]['styleDiff']!r}"
    )
    # A node that genuinely departs from its parent still reports.
    assert normalized["children"][0]["children"][0]["styleDiff"] == {
        "color-scheme": "dark"
    }, (
        "de-duplicating against the parent must not silence a node that "
        "genuinely departs from it; got "
        f"{normalized['children'][0]['children'][0]['styleDiff']!r}"
    )


def test_a_shadow_of_only_transparent_layers_becomes_none() -> None:
    """With nothing left to paint, the value is reported as `none`."""
    placeholder = "rgba(0, 0, 0, 0.000) 0px 0px 0px 0px"
    collapsed = weaver_snapshot._canonical_shadow(placeholder)
    assert collapsed == "none", (
        "a shadow whose every layer is transparent paints nothing, so it "
        f"should normalize to 'none'; {placeholder!r} gave {collapsed!r}"
    )


def test_transparent_shadow_layers_are_dropped_whatever_their_geometry() -> None:
    """Alpha decides whether a layer paints, not its offset or blur.

    Matching the fully-zero placeholder by its exact text kept any transparent
    layer that carried an offset, a blur or a spread, so two snapshots could
    differ over a shadow neither of them drew.
    """
    geometry = "rgba(0, 0, 0, 0.000) 2px 4px 6px 0px"
    dropped = weaver_snapshot._canonical_shadow(geometry)
    assert dropped == "none", (
        "a transparent layer paints nothing whatever its offset, blur or "
        f"spread, so it should be dropped; {geometry!r} gave {dropped!r}"
    )

    visible = "rgba(25, 60, 110, 0.100) 4px 4px 0px 0px"
    kept = weaver_snapshot._canonical_shadow(f"{geometry}, {visible}")
    assert kept == visible, (
        "dropping the transparent layer must leave the visible one intact; "
        f"expected {visible!r}, got {kept!r}"
    )


# --- The command boundary -------------------------------------------------
#
# Everything above tests normalization, which is where the subtle bugs are but
# not where the harness meets the world. These cover the commands themselves:
# what argv they build, what they do when a tool fails, and — for `diff` — the
# exit status that lets it gate a milestone.


def _snapshot(tmp_path: Path, name: str, **style: str) -> Path:
    """Write a minimal css-view snapshot file and return its path."""
    payload = {
        "payload": {
            "tree": {
                "tag": "div",
                "classes": [],
                "styleDiff": dict(style),
                "children": [],
            }
        }
    }
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_the_css_view_argv_pins_the_browser_and_names_the_output() -> None:
    """A comparison is only meaningful if both sides rendered the same way."""
    argv = weaver_snapshot._css_view_argv(
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
    argv = weaver_snapshot._screenshot_argv(Path("/out/home@360.png"))

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
    name = weaver_snapshot._session_name()

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
    weaver_snapshot._capture_pages(
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
    """A tool that exits non-zero must not leave a partial snapshot passing."""

    def explode(argv: cabc.Sequence[str]) -> None:
        raise subprocess.CalledProcessError(1, list(argv))

    with pytest.raises(subprocess.CalledProcessError):
        weaver_snapshot._capture_pages(
            ["", "install/"], Path("/out"), "http://x", "/usr/bin/bun", explode
        )


def test_shots_closes_its_session_even_when_a_page_fails() -> None:
    """An interrupted run must not strand a daemon holding the viewport."""
    calls: list[list[str]] = []

    def fail_on_screenshot(argv: cabc.Sequence[str]) -> None:
        calls.append(list(argv))
        if "screenshot" in argv:
            raise subprocess.CalledProcessError(1, list(argv))

    with pytest.raises(subprocess.CalledProcessError):
        weaver_snapshot._shoot_pages(
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
        weaver_snapshot._shoot_pages(
            [""], Path("/out"), "http://x", "/usr/bin/agent-browser", fail_everything
        )

    assert "close" not in caught.value.cmd, (
        f"the surfaced error should be the page's, not the cleanup's; got "
        f"{caught.value.cmd!r}"
    )


def test_every_page_is_shot_at_every_width() -> None:
    """A width that quietly captured nothing would look like a clean run."""
    calls: list[list[str]] = []
    weaver_snapshot._shoot_pages(
        ["", "install/"],
        Path("/out"),
        "http://x",
        "/usr/bin/agent-browser",
        lambda argv: calls.append(list(argv)),
    )

    shots = [argv[2] for argv in calls if argv[1] == "screenshot"]
    expected = [
        f"/out/{slug}@{width}.png"
        for width in weaver_snapshot.SCREENSHOT_WIDTHS
        for slug in (weaver_snapshot._slug(""), weaver_snapshot._slug("install/"))
    ]
    assert shots == expected, f"expected {expected!r}, got {shots!r}"


def test_diff_reports_no_differences_and_exits_cleanly(tmp_path: Path) -> None:
    """Two identical captures are not a change, so nothing should be raised."""
    before, after = tmp_path / "before", tmp_path / "after"
    before.mkdir()
    after.mkdir()
    _snapshot(before, "home", color="rgb(1, 2, 3)")
    _snapshot(after, "home", color="rgb(1, 2, 3)")

    weaver_snapshot.diff(before, after)


def test_diff_exits_non_zero_when_a_page_changed(tmp_path: Path) -> None:
    """The exit status is what lets this gate a milestone."""
    before, after = tmp_path / "before", tmp_path / "after"
    before.mkdir()
    after.mkdir()
    _snapshot(before, "home", color="rgb(1, 2, 3)")
    _snapshot(after, "home", color="rgb(9, 9, 9)")

    with pytest.raises(SystemExit) as caught:
        weaver_snapshot.diff(before, after)
    assert caught.value.code == 1, (
        f"a changed page should exit 1, not {caught.value.code!r}"
    )


def test_diff_ignores_a_change_the_normalization_calls_incidental(
    tmp_path: Path,
) -> None:
    """The same colour in two notations is not a difference worth reporting."""
    before, after = tmp_path / "before", tmp_path / "after"
    before.mkdir()
    after.mkdir()
    _snapshot(before, "home", color="rgb(1, 2, 3)")
    _snapshot(after, "home", color="rgba(1, 2, 3, 1)")

    weaver_snapshot.diff(before, after)


def test_a_page_missing_from_the_candidate_counts_as_a_difference(
    tmp_path: Path,
) -> None:
    """A page that stopped being published is a change, not an absence."""
    before, after = tmp_path / "before", tmp_path / "after"
    before.mkdir()
    after.mkdir()
    _snapshot(before, "home", color="rgb(1, 2, 3)")
    _snapshot(before, "install", color="rgb(1, 2, 3)")
    _snapshot(after, "home", color="rgb(1, 2, 3)")

    with pytest.raises(SystemExit) as caught:
        weaver_snapshot.diff(before, after)
    assert caught.value.code == 1, "a missing page should fail the comparison"


def test_a_page_only_in_the_candidate_counts_as_a_difference(
    tmp_path: Path,
) -> None:
    """A new page is as much a change as an altered one."""
    before, after = tmp_path / "before", tmp_path / "after"
    before.mkdir()
    after.mkdir()
    _snapshot(before, "home", color="rgb(1, 2, 3)")
    _snapshot(after, "home", color="rgb(1, 2, 3)")
    _snapshot(after, "install", color="rgb(1, 2, 3)")

    with pytest.raises(SystemExit) as caught:
        weaver_snapshot.diff(before, after)
    assert caught.value.code == 1, "a new page should fail the comparison"


def test_diff_says_so_rather_than_passing_on_an_empty_baseline(
    tmp_path: Path,
) -> None:
    """An empty baseline would otherwise compare zero pages and report success."""
    before, after = tmp_path / "before", tmp_path / "after"
    before.mkdir()
    after.mkdir()

    with pytest.raises(SystemExit) as caught:
        weaver_snapshot.diff(before, after)
    assert "no snapshots" in str(caught.value.code), (
        f"expected a message naming the empty directory; got {caught.value.code!r}"
    )


def test_publishing_clears_only_the_extension_being_written(tmp_path: Path) -> None:
    """A capture and a screenshot run share a directory, so each clears its own.

    Clearing happens at publication rather than before the capture: emptying
    the destination up front destroys the previous run's results in exchange
    for nothing, and leaves nothing behind if this run then fails.
    """
    out = tmp_path / "shots"
    out.mkdir()
    (out / "gone.json").write_text("{}", encoding="utf-8")
    (out / "kept.png").write_text("x", encoding="utf-8")

    with weaver_snapshot._staged(out, ".json") as stage:
        assert (out / "gone.json").exists(), (
            "the previous run's results should survive until this one succeeds"
        )
        (stage / "fresh.json").write_text("{}", encoding="utf-8")

    assert not (out / "gone.json").exists(), "the previous run's JSON should be cleared"
    assert (out / "fresh.json").exists(), "this run's snapshot should be published"
    assert (out / "kept.png").exists(), (
        "only the extension being written should be cleared, so a capture and "
        "a screenshot run can share a directory"
    )


def test_a_missing_tool_names_itself_rather_than_failing_obscurely() -> None:
    """`FileNotFoundError` from deep inside subprocess helps nobody."""
    with pytest.raises(SystemExit) as caught:
        weaver_snapshot._tool("definitely-not-a-real-tool-name")
    assert "definitely-not-a-real-tool-name" in str(caught.value.code), (
        f"the message should name the missing tool; got {caught.value.code!r}"
    )


@pytest.mark.parametrize(
    ("page", "slug"),
    [
        ("", "__home"),
        ("/", "__home"),
        ("install/", "install"),
        ("commands/act/", "commands__act"),
        # A page whose directory carries an underscore must not flatten onto
        # the stem a nested page would produce.
        ("what_next/", "what_unext"),
        ("what/next/", "what__next"),
    ],
)
def test_a_page_path_becomes_a_flat_filename_stem(page: str, slug: str) -> None:
    """Snapshots sit in one directory, so the slug carries the whole path."""
    assert weaver_snapshot._slug(page) == slug, (
        f"{page!r} should slug to {slug!r}, got {weaver_snapshot._slug(page)!r}"
    )


def test_the_snapshot_port_refuses_to_borrow_someone_else_s_server() -> None:
    """Polling a port someone else holds would snapshot their pages, not ours."""
    # `_served` checks for the server binary before it looks at the port, so
    # without `bun install` this would pass on the wrong SystemExit: the
    # message would name the missing binary and the port assertion below would
    # fail for a reason that has nothing to do with the behaviour under test.
    if not weaver_snapshot.HTTP_SERVER.is_file():  # pragma: no cover - env guard
        pytest.skip(
            f"{weaver_snapshot.HTTP_SERVER} is missing; run 'bun install' to "
            "exercise the port guard"
        )

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as squatter:
        squatter.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        squatter.bind(("127.0.0.1", 0))
        squatter.listen(1)
        port = squatter.getsockname()[1]

        with pytest.raises(SystemExit) as caught, weaver_snapshot._served(port):
            pass  # pragma: no cover - the context must not be entered

    assert str(port) in str(caught.value.code), (
        f"the message should name the occupied port; got {caught.value.code!r}"
    )


def test_a_parsed_snapshot_renders_without_touching_the_filesystem() -> None:
    """The rendering is pure, so it can be checked on a literal payload."""
    payload = {
        "meta": {"url": "http://127.0.0.1:8099/weaver/", "browser": "chromium"},
        "payload": {
            "tree": {
                "tag": "html",
                "styleDiff": {"--tw-ring-color": "rgb(1, 2, 3)", "color": "#ffffff"},
                "children": [],
            }
        },
    }
    rendered = weaver_snapshot._rendered_tree(payload)

    assert "--tw-ring-color" not in rendered, (
        f"the Tailwind internal survived into {rendered!r}"
    )
    assert "chromium" not in rendered, (
        "the capture envelope records when a snapshot was taken, not what the "
        f"page looks like, so it must not reach the diff; got {rendered!r}"
    )


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        pytest.param("{ not json", "not valid JSON", id="truncated"),
        pytest.param('{"payload": {}}', "payload.tree", id="wrong-shape"),
        pytest.param('{"payload": null}', "payload.tree", id="null-payload"),
        pytest.param("[]", "payload.tree", id="not-a-mapping"),
    ],
)
def test_an_unusable_snapshot_names_the_file_it_came_from(
    tmp_path: Path, content: str, expected: str
) -> None:
    """A traceback partway through a diff hides the one thing needed: which file."""
    snapshot = tmp_path / "install.json"
    snapshot.write_text(content, encoding="utf-8")

    with pytest.raises(SystemExit) as caught:
        weaver_snapshot._normalized_tree(snapshot)

    message = str(caught.value.code)
    assert str(snapshot) in message, (
        f"the message should name the file; got {message!r}"
    )
    assert expected in message, f"expected {expected!r} in {message!r}"


def test_a_missing_snapshot_exits_rather_than_raising_oserror(tmp_path: Path) -> None:
    """`diff` guards the candidate but reads the baseline by glob, not by check."""
    absent = tmp_path / "gone.json"

    with pytest.raises(SystemExit) as caught:
        weaver_snapshot._normalized_tree(absent)

    assert str(absent) in str(caught.value.code), (
        f"the message should name the file; got {caught.value.code!r}"
    )


def _lock_on(
    monkeypatch: pytest.MonkeyPatch, lock: Path, *, timeout: float = 0.2
) -> None:
    """Point the startup lock at a scratch file and shorten its wait."""
    monkeypatch.setattr(weaver_snapshot, "_lock_path", lambda _port: lock)
    monkeypatch.setattr(weaver_snapshot, "LOCK_TIMEOUT_SECONDS", timeout)


def test_the_startup_lock_is_exclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two runs must not both get past the probe and both spawn a server."""
    lock = tmp_path / "port.lock"
    _lock_on(monkeypatch, lock)

    # A second open file description on the same file is what a concurrent run
    # would have, so `flock` treats it as one.
    with (
        weaver_snapshot._startup_lock(8099),
        pytest.raises(SystemExit) as caught,
        weaver_snapshot._startup_lock(8099),
    ):
        pass  # pragma: no cover - the lock must not be granted twice

    message = str(caught.value.code)
    assert "8099" in message, f"the message should name the port; got {message!r}"
    assert str(lock) in message, f"the message should name the lock; got {message!r}"


def test_the_startup_lock_is_released_when_the_run_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run that exits mid-start must not leave the next one waiting it out."""
    lock = tmp_path / "port.lock"
    _lock_on(monkeypatch, lock)

    with pytest.raises(RuntimeError), weaver_snapshot._startup_lock(8099):
        raise RuntimeError(_MID_START_FAILURE)

    # The lock must be free now, or a failed run would poison the port until
    # its file was removed by hand.
    with weaver_snapshot._startup_lock(8099):
        pass


def test_the_lock_file_is_named_for_the_port_and_the_user() -> None:
    """Two ports must not serialize against each other, nor two users contend."""
    first = weaver_snapshot._lock_path(8099)
    second = weaver_snapshot._lock_path(8100)

    assert first != second, f"both ports would serialize on {first}"
    assert str(os.getuid()) in first.name, (
        f"a shared /tmp is sticky, so the name needs the uid; got {first.name!r}"
    )


def test_a_server_that_died_before_answering_is_not_taken_for_the_responder() -> None:
    """Something else answered on the port, and capturing it would be wrong."""

    class _Exited:
        """A child that answered nothing because it was never alive."""

        def poll(self) -> int | None:
            """Report the exit status `_await_server` asks for."""
            return 1

    with pytest.raises(SystemExit) as caught:
        weaver_snapshot._await_server(_Exited(), "http://127.0.0.1:8099", 8099)

    assert "8099" in str(caught.value.code), (
        f"the message should name the port; got {caught.value.code!r}"
    )


def test_a_server_that_dies_after_answering_is_not_taken_for_the_responder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reply proves something is listening, not that it is this run's server.

    The bind probe and the startup lock make this unreachable between two runs
    of this script, but nothing stops an unrelated server from claiming the
    port in the moment between the probe and the spawn. The ownership check is
    what turns that into a refusal rather than a snapshot of someone else's
    pages.
    """
    replies = iter([None, 0])

    class _DiesAfterReplying:
        """Alive when asked before the request, exited when asked after it."""

        def poll(self) -> int | None:
            """Report alive, then exited, so the reply lands in between."""
            return next(replies)

    monkeypatch.setattr(
        weaver_snapshot.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: contextlib.nullcontext(),
    )

    with pytest.raises(SystemExit) as caught:
        weaver_snapshot._await_server(
            _DiesAfterReplying(), "http://127.0.0.1:8099", 8099
        )

    message = str(caught.value.code)
    assert "another server" in message, (
        f"the message should say the reply was not this run's; got {message!r}"
    )


def test_the_port_is_probed_with_the_startup_lock_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Probing outside the lock is the check-then-act the lock exists to remove.

    If the probe ran before the lock were taken, two runs could still both
    find the port free and both go on to spawn — the ordering is the whole
    mechanism, so it is asserted rather than assumed.
    """
    lock = tmp_path / "port.lock"
    monkeypatch.setattr(weaver_snapshot, "_lock_path", lambda _port: lock)

    held: list[bool] = []

    def probe(_port: int) -> None:
        # An exclusive lock cannot be taken twice, so failing to take it here
        # is how holding it is observed.
        with lock.open("r+", encoding="utf-8") as rival:
            try:
                fcntl.flock(rival, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                held.append(True)
            else:
                fcntl.flock(rival, fcntl.LOCK_UN)
                held.append(False)
        message = "stop before spawning anything"
        raise SystemExit(message)

    monkeypatch.setattr(weaver_snapshot, "_refuse_occupied_port", probe)

    with pytest.raises(SystemExit):
        weaver_snapshot._start_server(8099, "weaver-snapshot-deadbeef.txt")

    assert held == [True], (
        "the port must be probed while the startup lock is held, or two runs "
        f"can still interleave; observed {held!r}"
    )


def test_an_unnamed_port_is_asked_for_rather_than_assumed() -> None:
    """Two runs cannot contend over a port the kernel picked for each of them."""
    first = weaver_snapshot._resolve_port(0)
    second = weaver_snapshot._resolve_port(0)

    for port in (first, second):
        assert port > 0, f"the kernel should have named a port; got {port!r}"
    named = 8099
    assert weaver_snapshot._resolve_port(named) == named, (
        "a port named explicitly should be honoured as given"
    )


def test_choosing_a_port_is_separable_from_obtaining_one() -> None:
    """The decision is pure; only the allocator touches the network.

    Splitting them is what lets the decision be checked without a socket — and
    what keeps the one function that can fail for reasons outside this process
    at the edge, where the command composes it.
    """
    allocated = 4321
    asked: list[int] = []

    def allocator() -> int:
        asked.append(allocated)
        return allocated

    assert weaver_snapshot._resolve_port(0, allocator) == allocated, (
        "an unnamed port should come from the allocator it was given"
    )
    assert asked == [allocated], (
        f"the allocator should be called exactly once; got {asked}"
    )

    asked.clear()
    assert weaver_snapshot._resolve_port(PORT, allocator) == PORT, (
        "a named port should be honoured without allocating anything"
    )
    assert asked == [], (
        "a named port should not have asked the allocator for one at all"
    )


def test_a_machine_with_no_free_port_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """The one environmental failure in port selection should not be a traceback."""

    class _Refusing:
        """A socket that cannot be bound, as an exhausted machine's would be."""

        def __enter__(self) -> _Refusing:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

        def bind(self, _address: tuple[str, int]) -> None:
            message = "Address family not supported"
            raise OSError(message)

    monkeypatch.setattr(weaver_snapshot.socket, "socket", lambda *_a, **_k: _Refusing())

    with pytest.raises(SystemExit) as caught:
        weaver_snapshot._allocate_port()

    assert "--port" in str(caught.value.code), (
        f"the message should name the way out; got {caught.value.code!r}"
    )


def test_the_ownership_marker_is_served_and_then_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The marker has to be reachable while serving and gone afterwards."""
    public = tmp_path / "public"
    public.mkdir()
    monkeypatch.setattr(weaver_snapshot, "REPO_ROOT", tmp_path)

    with weaver_snapshot._ownership_marker() as marker:
        placed = public / marker
        assert placed.is_file(), f"expected the marker at {placed}"
        assert placed.read_text(encoding="utf-8") == marker, (
            "the marker's contents name it, so a server that truncates or "
            "rewrites files cannot pass the check by accident"
        )

    assert not placed.exists(), f"{placed} was left behind in the served tree"


def test_two_runs_are_given_different_ownership_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A shared name would let either run's server satisfy the other's check."""
    public = tmp_path / "public"
    public.mkdir()
    monkeypatch.setattr(weaver_snapshot, "REPO_ROOT", tmp_path)

    with (
        weaver_snapshot._ownership_marker() as first,
        weaver_snapshot._ownership_marker() as second,
    ):
        assert first != second, f"both runs were given {first!r}"


@contextlib.contextmanager
def _serving(directory: Path) -> cabc.Iterator[str]:
    """Serve ``directory`` on a throwaway port for the duration of the context.

    `shutdown` stops `serve_forever`'s loop but leaves the listening socket
    open; only `server_close` releases it. Without both, each of these tests
    leaks a socket, and the next one can be handed a port the previous
    server's thread has not finished letting go of. Joining the thread is what
    makes "finished" true rather than probable.

    Yields
    ------
    str
        The origin it is listening on, without a trailing slash.
    """
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(directory)
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        serving.join(timeout=10)


def test_another_worktree_s_server_on_the_port_is_refused(tmp_path: Path) -> None:
    """Refuse a server that answers on the port but serves another tree.

    The startup lock is keyed on the user id, so two users racing for one port
    are not serialized by it — deliberately, since a sticky `/tmp` would make
    another user's lock file unopenable. And a running child says only that
    *something* of ours is alive, not that it is what answered. A server
    belonging to another worktree answers a readiness poll perfectly well and
    would have its pages captured as this branch's work.

    A lock cannot catch this and liveness cannot detect it; fetching a marker
    only this run knows the name of settles it.
    """
    theirs = tmp_path / "their-public"
    theirs.mkdir()
    (theirs / "index.html").write_text("<html>not ours</html>", encoding="utf-8")
    with _serving(theirs) as base, pytest.raises(SystemExit) as caught:
        weaver_snapshot._confirm_ownership(
            base, "weaver-snapshot-deadbeef.txt", PORT, "on starting"
        )

    message = str(caught.value.code)
    assert "8099" in message, f"the message should name the port; got {message!r}"
    assert "other tree" in message, (
        f"the message should say whose tree is being served; got {message!r}"
    )


def test_our_own_server_passes_the_ownership_check(tmp_path: Path) -> None:
    """The check must not refuse the server it was meant to accept."""
    ours = tmp_path / "public"
    ours.mkdir()
    marker = "weaver-snapshot-0123456789abcdef.txt"
    (ours / marker).write_text(marker, encoding="utf-8")
    with _serving(ours) as base:
        weaver_snapshot._confirm_ownership(base, marker, PORT, "on starting")


def test_a_server_that_returns_the_wrong_marker_is_refused(tmp_path: Path) -> None:
    """A tree that happens to hold that name is still not this run's tree."""
    theirs = tmp_path / "public"
    theirs.mkdir()
    marker = "weaver-snapshot-0123456789abcdef.txt"
    (theirs / marker).write_text("something else entirely", encoding="utf-8")
    with _serving(theirs) as base, pytest.raises(SystemExit) as caught:
        weaver_snapshot._confirm_ownership(base, marker, PORT, "on starting")

    assert "another server" in str(caught.value.code), (
        f"expected the mismatch to be reported; got {caught.value.code!r}"
    )


def test_the_server_is_offered_only_to_this_machine() -> None:
    """`http-server` defaults to 0.0.0.0, which publishes the tree to the LAN.

    The tree being served is an unreleased sub-site mid-migration, and every
    request this script makes is to loopback, so there is nothing to gain from
    the default and a disclosure to lose. Verified against the packaged
    binary's own help text, which documents `-a` as defaulting to `0.0.0.0`.
    """
    argv = weaver_snapshot._server_argv(8099)

    assert "-a" in argv, f"no address was pinned, so the default applies: {argv}"
    assert argv[argv.index("-a") + 1] == "127.0.0.1", (
        f"the address should be loopback; got {argv}"
    )


def test_the_server_argv_still_names_the_port_and_the_tree() -> None:
    """Pinning the address must not have displaced anything else."""
    argv = weaver_snapshot._server_argv(9123)

    assert argv[0] == str(weaver_snapshot.HTTP_SERVER), f"wrong executable: {argv}"
    assert "public" in argv, f"the published tree should be served: {argv}"
    assert argv[argv.index("-p") + 1] == "9123", f"the port should be passed: {argv}"


def test_a_page_list_is_taken_from_the_tree_it_is_given(tmp_path: Path) -> None:
    """The traversal is passed its root, so it can be exercised on a real one."""
    for page in ("", "install", "commands/act"):
        directory = tmp_path / page if page else tmp_path
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "index.html").write_text("<html></html>", encoding="utf-8")

    assert weaver_snapshot._page_paths(tmp_path) == ["", "commands/act/", "install/"], (
        f"got {weaver_snapshot._page_paths(tmp_path)!r}"
    )


def test_an_unreadable_corner_of_the_tree_stops_the_capture(tmp_path: Path) -> None:
    """A short page list is worse than a failure: it compares clean.

    `rglob` swallows an `OSError` on a descendant and yields nothing further
    beneath it, so a directory this process cannot read would quietly shorten
    the list. The pages under it would be absent from the capture and absent
    from the diff, which reads as "no differences" rather than "not looked at".
    """
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    closed = tmp_path / "closed"
    closed.mkdir()
    (closed / "index.html").write_text("<html></html>", encoding="utf-8")
    closed.chmod(0o000)
    try:
        if os.getuid() == 0:  # pragma: no cover - root ignores the mode
            pytest.skip("running as root, which can read the directory anyway")
        with pytest.raises(SystemExit) as caught:
            weaver_snapshot._page_paths(tmp_path)
    finally:
        closed.chmod(0o755)

    assert "could not be read" in str(caught.value.code), (
        f"the message should say what failed; got {caught.value.code!r}"
    )


def test_a_capture_is_published_only_once_it_is_whole(tmp_path: Path) -> None:
    """A run that fails partway must not leave half a capture to be compared."""
    out_dir = tmp_path / "snapshots"
    out_dir.mkdir()
    (out_dir / "__home.json").write_text("previous run", encoding="utf-8")

    def half_a_capture() -> None:
        """Write one page, then fail the way an interrupted run does."""
        with weaver_snapshot._staged(out_dir, ".json") as stage:
            (stage / "__home.json").write_text("this run", encoding="utf-8")
            raise RuntimeError(_MID_START_FAILURE)

    with pytest.raises(RuntimeError):
        half_a_capture()

    assert (out_dir / "__home.json").read_text(encoding="utf-8") == "previous run", (
        "a failed run replaced the previous capture with its own partial one"
    )
    assert not list(tmp_path.glob(".snapshots-*")), (
        f"the staging directory was left behind: {list(tmp_path.iterdir())}"
    )


def test_a_finished_capture_replaces_the_previous_one(tmp_path: Path) -> None:
    """Publication clears what was there, so a dropped page cannot linger."""
    out_dir = tmp_path / "snapshots"
    out_dir.mkdir()
    (out_dir / "__home.json").write_text("previous run", encoding="utf-8")
    (out_dir / "gone.json").write_text("a page that no longer exists", encoding="utf-8")

    with weaver_snapshot._staged(out_dir, ".json") as stage:
        (stage / "__home.json").write_text("this run", encoding="utf-8")

    assert (out_dir / "__home.json").read_text(encoding="utf-8") == "this run", (
        "a capture that finished did not replace the previous run's snapshot, "
        "so the diff would compare the baseline against itself"
    )
    assert not (out_dir / "gone.json").exists(), (
        "a snapshot from a previous run survived, and would be compared as "
        "though this run had written it"
    )
    assert not list(tmp_path.glob(".snapshots-*")), "the staging directory was left"


def test_two_runs_publishing_the_same_directory_contend(tmp_path: Path) -> None:
    """Publication is the moment two runs would interleave, so it is serialized."""
    out_dir = tmp_path / "snapshots"
    out_dir.mkdir()
    first = weaver_snapshot._output_lock_path(out_dir.resolve())
    second = weaver_snapshot._output_lock_path((tmp_path / "other").resolve())

    assert first == weaver_snapshot._output_lock_path(out_dir.resolve()), (
        "one directory should map to one lock, however often it is asked for"
    )
    assert first != second, f"two directories both locked on {first}"


@pytest.mark.parametrize(
    ("shape", "expected"),
    [
        pytest.param(
            {"tag": "html", "children": ["oops"]},
            "payload.tree.children[0]",
            id="child-is-a-string",
        ),
        pytest.param([1, 2], "payload.tree", id="tree-is-a-list"),
        pytest.param("nope", "payload.tree", id="tree-is-a-string"),
        pytest.param(
            {"tag": "html", "styleDiff": [1], "children": []},
            "styleDiff",
            id="style-diff-is-a-list",
        ),
        pytest.param(
            {"tag": "html", "children": "abc"},
            "children",
            id="children-is-a-string",
        ),
        pytest.param(
            {
                "tag": "html",
                "children": [{"tag": "a", "children": [{"tag": "b", "children": [7]}]}],
            },
            "children[0].children[0].children[0]",
            id="a-node-three-levels-down",
        ),
    ],
)
def test_a_snapshot_that_is_not_the_expected_shape_says_where(
    tmp_path: Path,
    shape: dict[str, object] | list[object] | str,
    expected: str,
) -> None:
    """The normalization reaches for `.get` on every node, so a scalar is fatal.

    Before the shape was checked, each of these surfaced from deep inside the
    recursion as `'str' object has no attribute 'get'` — an `AttributeError`,
    which the read boundary did not catch, naming neither the file nor the
    node. A snapshot from an interrupted capture or a different tool looks
    exactly like this.
    """
    snapshot = tmp_path / "install.json"
    snapshot.write_text(json.dumps({"payload": {"tree": shape}}), encoding="utf-8")

    with pytest.raises(SystemExit) as caught:
        weaver_snapshot._normalized_tree(snapshot)

    message = str(caught.value.code)
    assert str(snapshot) in message, (
        f"the message should name the file; got {message!r}"
    )
    assert expected in message, (
        f"the message should point at {expected!r}; got {message!r}"
    )


def test_a_well_formed_snapshot_is_still_accepted(tmp_path: Path) -> None:
    """A shape check that rejected valid input would be worse than none."""
    snapshot = tmp_path / "install.json"
    snapshot.write_text(
        json.dumps(
            {
                "payload": {
                    "tree": {
                        "tag": "html",
                        "styleDiff": {"color": "rgb(1, 2, 3)"},
                        "children": [{"tag": "body", "children": []}, {"tag": "div"}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    rendered = weaver_snapshot._normalized_tree(snapshot)

    assert "rgba(1, 2, 3, 1.000)" in rendered, (
        f"the tree should have normalized rather than been rejected; got {rendered!r}"
    )


def test_a_diff_takes_the_same_lock_publication_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A reader that started midway would compare two runs against each other.

    Publication replaces file by file. Each replacement is atomic, the
    sequence of them is not, and a diff running through that sequence would
    take some pages from this run and some from the last — then report the
    difference as the branch's work. The reader taking the writer's lock is
    what closes it.
    """
    before = tmp_path / "baseline"
    after = tmp_path / "current"
    for directory in (before, after):
        directory.mkdir()
        (directory / "__home.json").write_text(
            json.dumps({"payload": {"tree": {"tag": "html", "children": []}}}),
            encoding="utf-8",
        )

    taken: list[Path] = []
    real = weaver_snapshot._exclusive

    @contextlib.contextmanager
    def watched(path: Path, contended: str) -> cabc.Iterator[None]:
        taken.append(path)
        with real(path, contended):
            yield

    monkeypatch.setattr(weaver_snapshot, "_exclusive", watched)
    weaver_snapshot.diff(before, after)

    expected = [
        weaver_snapshot._output_lock_path(directory.resolve())
        for directory in sorted((before.resolve(), after.resolve()))
    ]
    assert taken == expected, (
        f"the diff should lock both directories, in a stable order; it took "
        f"{taken} rather than {expected}"
    )


def test_two_readers_take_a_pair_of_directories_the_same_way_round(
    tmp_path: Path,
) -> None:
    """Opposite orders would let two diffs each hold what the other wants."""
    first = tmp_path / "aaa"
    second = tmp_path / "zzz"
    for directory in (first, second):
        directory.mkdir()

    assert weaver_snapshot._reading_order(
        first, second
    ) == weaver_snapshot._reading_order(second, first), (
        "the order must not depend on which argument the directory arrived as"
    )


def test_one_directory_named_twice_is_locked_once(tmp_path: Path) -> None:
    """`flock` on the same file twice from one process would block forever."""
    same = tmp_path / "snapshots"
    same.mkdir()

    assert weaver_snapshot._reading_order(same, same) == [same.resolve()], (
        f"got {weaver_snapshot._reading_order(same, same)!r}"
    )


@contextlib.contextmanager
def _driven(
    monkeypatch: pytest.MonkeyPatch, pages: list[str], tools: dict[str, str]
) -> cabc.Iterator[dict[str, typ.Any]]:
    """Run a command with every outward seam replaced, and record what it did.

    The commands are the part nobody had exercised: their helpers are covered
    one by one, and `capture` end to end through a real browser, but nothing
    checked that a command wires its helpers together in the right order with
    the right arguments. A command that resolved the wrong tool, served the
    wrong port, or staged the wrong suffix would pass every existing test.

    Yields
    ------
    dict
        ``argv`` — every command the run would have executed; ``served`` — the
        ports the server was asked for, and whether it was stopped; ``staged``
        — the (directory, suffix) pairs staged.
    """
    record: dict[str, typ.Any] = {"argv": [], "served": [], "staged": [], "closed": []}

    @contextlib.contextmanager
    def served(port: int, *_args: object, **_kwargs: object) -> cabc.Iterator[str]:
        record["served"].append(port)
        try:
            yield "http://127.0.0.1:9999"
        finally:
            record["closed"].append(port)

    @contextlib.contextmanager
    def staged(out_dir: Path, suffix: str) -> cabc.Iterator[Path]:
        record["staged"].append((out_dir, suffix))
        staging = out_dir / ".staging"
        staging.mkdir(parents=True, exist_ok=True)
        yield staging

    monkeypatch.setattr(weaver_snapshot, "_served", served)
    monkeypatch.setattr(weaver_snapshot, "_staged", staged)
    monkeypatch.setattr(weaver_snapshot, "_page_paths", lambda: list(pages))
    monkeypatch.setattr(weaver_snapshot, "_tool", lambda name: tools[name])
    monkeypatch.setattr(
        weaver_snapshot, "_run_tool", lambda argv: record["argv"].append(list(argv))
    )
    yield record


def test_the_shots_command_wires_its_helpers_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`shots` is a public command and had no test of its own at all."""
    pages = ["", "install/"]
    with _driven(
        monkeypatch, pages, {"agent-browser": "/usr/bin/agent-browser"}
    ) as run:
        weaver_snapshot.shots(tmp_path / "out", port=8123)

    assert run["served"] == [8123], (
        f"the port the caller named should reach the server; got {run['served']}"
    )
    assert run["closed"] == [8123], "the server should be stopped on the way out"
    assert run["staged"] == [(tmp_path / "out", ".png")], (
        f"screenshots should stage as .png; got {run['staged']}"
    )

    executables = {argv[0] for argv in run["argv"]}
    assert executables == {"/usr/bin/agent-browser"}, (
        f"every command should be the resolved browser; got {executables}"
    )

    shots = [argv[2] for argv in run["argv"] if argv[1] == "screenshot"]
    expected = [
        f"{tmp_path / 'out' / '.staging'}/{weaver_snapshot._slug(page)}@{width}.png"
        for width in weaver_snapshot.SCREENSHOT_WIDTHS
        for page in pages
    ]
    assert shots == expected, (
        f"expected one screenshot per page at every width, into the staging "
        f"directory; got {shots}"
    )


def test_the_capture_command_wires_its_helpers_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same for `capture`, whose only other coverage needs a real browser."""
    pages = ["", "commands/act/"]
    with _driven(monkeypatch, pages, {"bun": "/usr/bin/bun"}) as run:
        weaver_snapshot.capture(tmp_path / "out", port=8124)

    assert run["served"] == [8124], f"the named port should be served; got {run}"
    assert run["closed"] == [8124], f"and then stopped; got {run}"
    assert run["staged"] == [(tmp_path / "out", ".json")], (
        f"captures should stage as .json; got {run['staged']}"
    )

    outputs = [argv[argv.index("--output") + 1] for argv in run["argv"]]
    expected = [
        f"{tmp_path / 'out' / '.staging'}/{weaver_snapshot._slug(page)}.json"
        for page in pages
    ]
    assert outputs == expected, (
        f"expected one snapshot per page, into the staging directory; got {outputs}"
    )
    assert all(argv[0] == "/usr/bin/bun" for argv in run["argv"]), (
        f"every command should run through the resolved bun; got {run['argv']}"
    )


def test_a_command_stops_its_server_even_when_a_page_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A browser that fails on page two must not strand the server on port one."""
    with _driven(monkeypatch, ["", "install/"], {"bun": "/usr/bin/bun"}) as run:

        def refuse(_argv: cabc.Sequence[str]) -> None:
            raise subprocess.CalledProcessError(1, "bun")

        monkeypatch.setattr(weaver_snapshot, "_run_tool", refuse)
        with pytest.raises(subprocess.CalledProcessError):
            weaver_snapshot.capture(tmp_path / "out", port=8125)

    assert run["closed"] == [8125], (
        f"the server should be stopped however the run ends; got {run['closed']}"
    )


def test_the_port_probe_binds_the_way_the_server_will() -> None:
    """A stricter probe refuses a port the server would have taken.

    `http-server` sets SO_REUSEADDR, so it binds a port whose last connection
    is still in TIME_WAIT. Without the same option the probe fails where the
    server would succeed, and a capture is refused for a minute after the last
    one on a port nothing is really using.

    The state has to be produced rather than assumed: closing a listening
    socket that never accepted anything does not enter TIME_WAIT. A connection
    has to be made and closed from the listening side first.
    """
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port))
    accepted, _peer = listener.accept()
    accepted.close()  # the listening side closes first, so its end waits
    client.close()
    listener.close()

    # Precondition: this is the state the probe has to tolerate. Without it
    # the test would pass on a port that is simply free.
    bare = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(OSError, match="in use"):
            bare.bind(("127.0.0.1", port))
    finally:
        bare.close()

    weaver_snapshot._refuse_occupied_port(port)


def test_a_symlink_where_the_lock_belongs_is_refused(tmp_path: Path) -> None:
    """The lock's path is predictable and its directory is world-writable.

    Another user can put a symlink there first. `open("w")` would follow it and
    truncate whatever it pointed at — something of ours, chosen by them.
    """
    victim = tmp_path / "something-of-ours.txt"
    victim.write_text("must survive", encoding="utf-8")
    lock = tmp_path / "port.lock"
    lock.symlink_to(victim)

    with pytest.raises(SystemExit) as caught, weaver_snapshot._lock_file(lock):
        pass  # pragma: no cover - the open must not succeed

    assert str(lock) in str(caught.value.code), (
        f"the message should name the lock; got {caught.value.code!r}"
    )
    assert victim.read_text(encoding="utf-8") == "must survive", (
        "the symlink was followed and its target truncated"
    )


def test_a_lock_path_that_is_not_a_regular_file_is_refused(tmp_path: Path) -> None:
    """Winning the race is not the same as being handed the right file.

    A FIFO rather than a directory, because `os.open` refuses a directory
    itself and the check under test is the one after the open succeeds.
    """
    lock = tmp_path / "port.lock"
    os.mkfifo(lock)

    with pytest.raises(SystemExit) as caught, weaver_snapshot._lock_file(lock):
        pass  # pragma: no cover - the open must not succeed

    assert "regular file" in str(caught.value.code), (
        f"the message should say what is wrong with it; got {caught.value.code!r}"
    )


def test_a_lock_belonging_to_another_user_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file another user got there first with is not this run's lock."""
    lock = tmp_path / "port.lock"
    lock.write_text("", encoding="utf-8")
    somebody_else = os.getuid() + 1
    monkeypatch.setattr(weaver_snapshot.os, "getuid", lambda: somebody_else)

    with pytest.raises(SystemExit) as caught, weaver_snapshot._lock_file(lock):
        pass  # pragma: no cover - the open must not succeed

    assert "belongs to uid" in str(caught.value.code), (
        f"the message should say whose it is; got {caught.value.code!r}"
    )


def test_an_existing_lock_file_is_not_truncated(tmp_path: Path) -> None:
    """Opening for writing would empty a file this process did not create."""
    lock = tmp_path / "port.lock"
    lock.write_text("a previous run left this", encoding="utf-8")

    with weaver_snapshot._lock_file(lock):
        pass

    assert lock.read_text(encoding="utf-8") == "a previous run left this", (
        "the lock file was truncated; the lock is the flock, not the contents"
    )


def test_a_failed_publication_leaves_the_destination_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deleting then moving is not atomic: a failure halfway loses both runs.

    The previous files are moved aside rather than deleted, so a rename that
    fails partway can be undone. Without that the destination ends up holding
    some of each with the originals already gone — the worst state, because it
    still looks like a directory of snapshots.
    """
    destination = tmp_path / "out"
    destination.mkdir()
    (destination / "one.json").write_text("previous one", encoding="utf-8")
    (destination / "two.json").write_text("previous two", encoding="utf-8")
    (destination / "kept.png").write_text("a screenshot run's", encoding="utf-8")

    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "one.json").write_text("this one", encoding="utf-8")
    (staging / "two.json").write_text("this two", encoding="utf-8")

    moves = {"n": 0}
    # Two rescues, then one publication, then the disk fills.
    breaks_on = 4

    def failing(source: Path, target: Path) -> object:
        moves["n"] += 1
        # Exactly one operation fails. A rename back into the directory the
        # file just left needs no new space, so a real ENOSPC would not block
        # the rollback either, and a mover that failed forever would test the
        # fake rather than the code.
        if moves["n"] == breaks_on:
            message = "no space left on device"
            raise OSError(message)
        return source.replace(target)

    with pytest.raises(OSError, match="no space left"):
        weaver_snapshot._publish(staging, destination, ".json", failing)

    assert (destination / "one.json").read_text(encoding="utf-8") == "previous one", (
        "a failed publication left this run's file in place of the previous one"
    )
    assert (destination / "two.json").read_text(encoding="utf-8") == "previous two", (
        "a failed publication lost the previous run's snapshot"
    )
    assert (destination / "kept.png").exists(), (
        "the other extension should not have been touched at all"
    )


def test_a_publication_that_succeeds_replaces_everything(tmp_path: Path) -> None:
    """The rollback path must not have cost the ordinary one its job."""
    destination = tmp_path / "out"
    destination.mkdir()
    (destination / "one.json").write_text("previous", encoding="utf-8")
    (destination / "gone.json").write_text("a page that no longer exists", "utf-8")
    (destination / "kept.png").write_text("a screenshot run's", encoding="utf-8")

    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "one.json").write_text("this run", encoding="utf-8")

    weaver_snapshot._publish(staging, destination, ".json")

    assert (destination / "one.json").read_text(encoding="utf-8") == "this run", (
        "a publication that succeeded did not replace the previous snapshot"
    )
    assert not (destination / "gone.json").exists(), (
        "a snapshot from a previous run survived this one"
    )
    assert (destination / "kept.png").exists(), "the other extension was touched"
