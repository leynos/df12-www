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
    assert weaver_snapshot._canonical_value(notation) == expected


def test_distinct_colours_stay_distinct() -> None:
    """Normalization must not collapse colours that genuinely differ.

    Tailwind v4 redefined its stock palette in OKLCH, so ``green-500`` moved
    from ``#22c55e`` to a slightly different green. That is a real change and
    the differ has to report it.
    """
    v3_green = weaver_snapshot._canonical_value("rgb(34, 197, 94)")
    v4_green = weaver_snapshot._canonical_value("oklch(0.723 0.219 149.579)")
    assert v3_green != v4_green


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
    )
    assert normalize(weaver_snapshot._canonical_value(v3)) == (
        "rgba(0, 0, 0, 0.050) 0px 1px 2px 0px"
    )


def test_a_real_shadow_change_survives_normalization() -> None:
    """Dropping placeholders must not hide a shadow that actually moved."""
    normalize = weaver_snapshot._canonical_shadow
    two_px = normalize("rgba(25, 60, 110, 1.000) 2px 2px 0px 0px")
    four_px = normalize("rgba(25, 60, 110, 1.000) 4px 4px 0px 0px")
    assert two_px != four_px


def _node(**style: str) -> dict[str, typ.Any]:
    """Build a minimal walker node carrying the given computed styles."""
    return {"tag": "div", "classes": [], "styleDiff": dict(style), "children": []}


def test_tailwind_internal_properties_are_ignored() -> None:
    """``--tw-*`` variables are plumbing, not something a reader can see."""
    normalized = weaver_snapshot._normalize(
        _node(**{"--tw-text-opacity": "1", "color": "rgb(1, 2, 3)"})
    )
    assert normalized["styleDiff"] == {"color": "rgba(1, 2, 3, 1.000)"}


def test_animated_opacity_is_ignored_but_static_opacity_is_not() -> None:
    """Only a node mid-animation should have its sampled opacity discarded."""
    animated = weaver_snapshot._normalize(
        _node(**{"animation-name": "pulse", "opacity": "0.694981"})
    )
    assert "opacity" not in animated["styleDiff"]

    static = weaver_snapshot._normalize(_node(opacity="0.5"))
    assert static["styleDiff"]["opacity"] == "0.5"


def test_normalization_recurses_into_children() -> None:
    """Nested nodes get the same treatment as the root."""
    tree = _node(color="rgb(1, 2, 3)")
    tree["children"] = [_node(**{"--tw-ring-offset-width": "0px"})]
    normalized = weaver_snapshot._normalize(tree)
    assert normalized["children"][0]["styleDiff"] == {}


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
    assert normalized["bbox"]["y"] == settled_y

    # The other half of the docstring's promise, which nothing checked: a
    # rounding that also swallowed real movement would make the whole
    # comparison worthless, and would have passed the assertion above.
    shifted = _node()
    shifted["bbox"] = {"x": 0.0, "y": jittered_y + 1, "width": 640.0, "height": height}
    assert (
        weaver_snapshot._normalize(shifted)["bbox"]["y"] != normalized["bbox"]["y"]
    ), "a one-pixel shift must survive normalization, or diffs mean nothing"
    assert normalized["bbox"]["height"] == height


def test_invisible_border_colours_are_ignored() -> None:
    """A colour on an undrawn border is not something a reader can see."""
    normalized = weaver_snapshot._normalize(
        _node(**{"border-top-color": "rgb(229, 231, 235)"})
    )
    assert normalized["styleDiff"] == {}


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
    assert normalized["styleDiff"]["border-top-color"] == "rgba(229, 231, 235, 1.000)"


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
    assert "border-top-color" in normalized["styleDiff"]


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
    assert normalized["styleDiff"] == {"color-scheme": "light"}
    assert normalized["children"][0]["styleDiff"] == {}
    # A node that genuinely departs from its parent still reports.
    assert normalized["children"][0]["children"][0]["styleDiff"] == {
        "color-scheme": "dark"
    }


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


def test_the_output_directory_is_cleared_of_the_previous_run(tmp_path: Path) -> None:
    """A stale snapshot left behind would be compared as though it were fresh."""
    out = tmp_path / "shots"
    out.mkdir()
    (out / "gone.json").write_text("{}", encoding="utf-8")
    (out / "kept.png").write_text("x", encoding="utf-8")

    resolved = weaver_snapshot._prepare_output_dir(out, ".json")

    assert not (out / "gone.json").exists(), "the previous run's JSON should be cleared"
    assert (out / "kept.png").exists(), (
        "only the extension being written should be cleared, so a capture and "
        "a screenshot run can share a directory"
    )
    assert resolved.is_absolute(), f"the path should be resolved; got {resolved!r}"


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
    monkeypatch.setattr(weaver_snapshot, "STARTUP_LOCK_TIMEOUT_SECONDS", timeout)


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


def test_the_ownership_marker_is_served_and_then_removed(tmp_path: Path) -> None:
    """The marker has to be reachable while serving and gone afterwards."""
    public = tmp_path / "public"
    public.mkdir()
    monkeypatched = pytest.MonkeyPatch()
    monkeypatched.setattr(weaver_snapshot, "REPO_ROOT", tmp_path)
    try:
        with weaver_snapshot._ownership_marker() as marker:
            placed = public / marker
            assert placed.is_file(), f"expected the marker at {placed}"
            assert placed.read_text(encoding="utf-8") == marker, (
                "the marker's contents name it, so a server that truncates or "
                "rewrites files cannot pass the check by accident"
            )
    finally:
        monkeypatched.undo()

    assert not placed.exists(), f"{placed} was left behind in the served tree"


def test_two_runs_are_given_different_ownership_markers(tmp_path: Path) -> None:
    """A shared name would let either run's server satisfy the other's check."""
    public = tmp_path / "public"
    public.mkdir()
    monkeypatched = pytest.MonkeyPatch()
    monkeypatched.setattr(weaver_snapshot, "REPO_ROOT", tmp_path)
    try:
        with (
            weaver_snapshot._ownership_marker() as first,
            weaver_snapshot._ownership_marker() as second,
        ):
            assert first != second, f"both runs were given {first!r}"
    finally:
        monkeypatched.undo()


def _serving(directory: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    """Start a throwaway server over ``directory`` and return it and its origin."""
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(directory)
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


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
    server, base = _serving(theirs)
    try:
        with pytest.raises(SystemExit) as caught:
            weaver_snapshot._confirm_ownership(
                base, "weaver-snapshot-deadbeef.txt", 8099, "on starting"
            )
    finally:
        server.shutdown()

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
    server, base = _serving(ours)
    try:
        weaver_snapshot._confirm_ownership(base, marker, 8099, "on starting")
    finally:
        server.shutdown()


def test_a_server_that_returns_the_wrong_marker_is_refused(tmp_path: Path) -> None:
    """A tree that happens to hold that name is still not this run's tree."""
    theirs = tmp_path / "public"
    theirs.mkdir()
    marker = "weaver-snapshot-0123456789abcdef.txt"
    (theirs / marker).write_text("something else entirely", encoding="utf-8")
    server, base = _serving(theirs)
    try:
        with pytest.raises(SystemExit) as caught:
            weaver_snapshot._confirm_ownership(base, marker, 8099, "on starting")
    finally:
        server.shutdown()

    assert "another server" in str(caught.value.code), (
        f"expected the mismatch to be reported; got {caught.value.code!r}"
    )
