"""What the harness removes from a captured tree, and what it must not.

Too little and every translucent colour on the site reports as changed,
burying the handful that really did; too much and a genuine regression is
normalized away and ships. These fix both edges.
"""

from __future__ import annotations

import typing as typ
from pathlib import Path

import pytest

from tests.support.weaver_harness import load

REPO_ROOT = Path(__file__).resolve().parents[1]

# Stands in for whatever goes wrong between taking a lock and the work
# finishing. Named so a `pytest.raises` block stays one statement.
_MID_START_FAILURE = "the port was occupied"

# A port number for the messages these tests read back. Nothing binds it.
PORT = 8099

normalize = load("weaver_snapshot_normalize")


def _node(**style: str) -> dict[str, typ.Any]:
    """Build a minimal walker node carrying the given computed styles."""
    return {"tag": "div", "classes": [], "styleDiff": dict(style), "children": []}


def test_tailwind_internal_properties_are_ignored() -> None:
    """``--tw-*`` variables are plumbing, not something a reader can see."""
    normalized = normalize._normalize(
        _node(**{"--tw-text-opacity": "1", "color": "rgb(1, 2, 3)"})
    )
    assert normalized["styleDiff"] == {"color": "rgba(1, 2, 3, 1.000)"}, (
        "`--tw-*` variables are Tailwind's plumbing and change between "
        f"versions without the page changing; got {normalized['styleDiff']!r}"
    )


def test_animated_opacity_is_ignored_but_static_opacity_is_not() -> None:
    """Only a node mid-animation should have its sampled opacity discarded."""
    animated = normalize._normalize(
        _node(**{"animation-name": "pulse", "opacity": "0.694981"})
    )
    assert "opacity" not in animated["styleDiff"], (
        "a node mid-animation reports whatever opacity the sample caught, "
        f"which differs run to run; got {animated['styleDiff']!r}"
    )

    static = normalize._normalize(_node(opacity="0.5"))
    assert static["styleDiff"]["opacity"] == "0.5", (
        "a static opacity is a real declaration and must survive; got "
        f"{static['styleDiff']!r}"
    )


def test_normalization_recurses_into_children() -> None:
    """Nested nodes get the same treatment as the root."""
    tree = _node(color="rgb(1, 2, 3)")
    tree["children"] = [_node(**{"--tw-ring-offset-width": "0px"})]
    normalized = normalize._normalize(tree)
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
    normalized = normalize._canonical_style(style_diff)

    assert style_diff == original, (
        f"_canonical_style must not modify its argument; it became {style_diff!r}"
    )
    assert normalized == {"color": "rgba(1, 2, 3, 1.000)"}, (
        "the returned styles should drop --tw-* plumbing and canonicalize the "
        f"colour; got {normalized!r}"
    )


def test_canonical_style_treats_an_absent_style_diff_as_empty() -> None:
    """A node with no styles of its own is not an error."""
    assert normalize._canonical_style(None) == {}, (
        "a missing styleDiff should normalize to an empty mapping"
    )


def test_resolve_tracked_reports_a_departure_and_carries_it_down() -> None:
    """A tracked property is kept only where the node overrides the parent."""
    style = {"color-scheme": "dark", "caret-color": "rgb(1, 2, 3)"}
    carried = normalize._resolve_tracked(
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
    normalize._resolve_tracked({"color-scheme": "dark"}, inherited)

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
    normalized = normalize._normalize(node)

    assert "bbox" in normalized, (
        f"the bbox key should be preserved for a {type(bbox).__name__} value"
    )
    assert normalized["bbox"] == bbox, (
        f"a non-mapping bbox should pass through unchanged; {bbox!r} became "
        f"{normalized['bbox']!r}"
    )


def test_a_node_without_a_bbox_does_not_gain_one() -> None:
    """Normalization reports what the walker saw, and invents nothing."""
    normalized = normalize._normalize(_node())
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
    normalized = normalize._normalize(node)
    assert normalized["bbox"]["y"] == settled_y, (
        f"subpixel jitter should round away, or every capture differs from "
        f"the last; {jittered_y} normalized to {normalized['bbox']['y']}"
    )

    # The other half of the docstring's promise, which nothing checked: a
    # rounding that also swallowed real movement would make the whole
    # comparison worthless, and would have passed the assertion above.
    shifted = _node()
    shifted["bbox"] = {"x": 0.0, "y": jittered_y + 1, "width": 640.0, "height": height}
    assert normalize._normalize(shifted)["bbox"]["y"] != normalized["bbox"]["y"], (
        "a one-pixel shift must survive normalization, or diffs mean nothing"
    )
    assert normalized["bbox"]["height"] == height, (
        f"a whole-number dimension should pass through untouched; {height} "
        f"became {normalized['bbox']['height']}"
    )


def test_invisible_border_colours_are_ignored() -> None:
    """A colour on an undrawn border is not something a reader can see."""
    normalized = normalize._normalize(
        _node(**{"border-top-color": "rgb(229, 231, 235)"})
    )
    assert normalized["styleDiff"] == {}, (
        "a colour on an edge of zero width paints nothing, so it is not a "
        f"difference a reader could see; got {normalized['styleDiff']!r}"
    )


def test_drawn_border_colours_are_kept() -> None:
    """Give an edge a width and its colour becomes a real difference again."""
    normalized = normalize._normalize(
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
    normalized = normalize._normalize(
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

    normalized = normalize._normalize(root)
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
