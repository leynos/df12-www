"""Tests for the Weaver computed-style snapshot harness.

The harness in ``scripts/weaver_snapshot.py`` is what the Tailwind v4 and
daisyUI v5 migration is judged by, so its normalization has to be right in
both directions. Too little and every translucent colour on the site reports
as changed, burying the handful that really did; too much and a genuine
regression is normalized away and ships.
"""

from __future__ import annotations

import importlib.util
import typing as typ
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

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
