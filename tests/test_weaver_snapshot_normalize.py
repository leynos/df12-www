"""What the harness removes from a captured tree, and what it must not.

Too little and every translucent colour on the site reports as changed,
burying the handful that really did; too much and a genuine regression is
normalized away and ships. These fix both edges.
"""

from __future__ import annotations

import typing as typ

import pytest

from tests.support.weaver_harness import load

normalize = load("weaver_snapshot_normalize")
folds = load("weaver_snapshot_folds")
transform = load("weaver_snapshot_transform")


def _node(**style: str) -> dict[str, typ.Any]:
    """Build a minimal walker node carrying the given computed styles."""
    return {"tag": "div", "classes": [], "styleDiff": dict(style), "children": []}


def test_tailwind_internal_properties_are_ignored() -> None:
    """Custom properties are plumbing, not something a reader can see.

    ``--tw-*`` are Tailwind's; ``--color-*`` and the rest are the theme's
    tokens on ``:root``, several hundred of them, each consumed by the
    visible property that would show a change.
    """
    normalized = normalize._normalize(
        _node(
            **{
                "--tw-text-opacity": "1",
                "--color-primary": "#2b4162",
                "color": "rgb(1, 2, 3)",
            }
        )
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


def test_an_animated_transform_and_box_are_ignored_but_static_ones_are_not() -> None:
    """A spinner reports whatever angle the sample caught; a rotated logo does not."""
    spinning = _node(
        **{
            "animation-name": "spin",
            "transform": "matrix(-0.99, 0.1, -0.1, -0.99, 0, 0)",
        }
    )
    spinning["bbox"] = {"x": 1122.64, "y": 674.64, "width": 10.72, "height": 10.72}
    normalized = normalize._normalize(spinning)
    assert "transform" not in normalized["styleDiff"], (
        f"a mid-spin transform differs run to run; got {normalized['styleDiff']!r}"
    )
    assert "bbox" not in normalized, (
        f"a spinning node's box turns with it; got {normalized.get('bbox')!r}"
    )

    # The path inside the spinning icon has no animation of its own and turns
    # with its parent all the same.
    spinning["children"] = [_node()]
    spinning["children"][0]["bbox"] = {"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0}
    assert "bbox" not in normalize._normalize(spinning)["children"][0], (
        "a box inside a spinning node turns with it and must go too"
    )

    still = _node(transform="matrix(0.99, 0.1, -0.1, 0.99, 0, 0)")
    still["bbox"] = {"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0}
    normalized = normalize._normalize(still)
    assert normalized["styleDiff"]["transform"] == still["styleDiff"]["transform"], (
        "a static transform is a real declaration and must survive"
    )
    assert normalized["bbox"] == still["bbox"], "a static node keeps its box"


def test_the_loopback_port_inside_a_url_is_ignored() -> None:
    """The server gets a new port per run, and a resolved url() carries it."""
    normalized = normalize._normalize(
        _node(**{"background-image": 'url("http://127.0.0.1:57909/netsuke/a.jpg")'})
    )
    assert normalized["styleDiff"]["background-image"] == (
        'url("http://127.0.0.1/netsuke/a.jpg")'
    ), f"the port should go and the path stay; got {normalized['styleDiff']!r}"

    elsewhere = _node(**{"background-image": 'url("http://example.com:8080/a.jpg")'})
    assert normalize._normalize(elsewhere)["styleDiff"] == elsewhere["styleDiff"], (
        "only the harness's own loopback origin is incidental"
    )


@pytest.mark.parametrize(
    ("minted", "stable"),
    [
        ("clip15905cxyplot", "clipxyplot"),
        ("clip15905cx", "clipx"),
        ("defs-15905c", "defs-"),
        ("topdefs-15905c", "topdefs-"),
        ("legend15905c", "legend"),
    ],
)
def test_a_plotly_uid_is_ignored_in_an_id_and_in_a_reference(
    minted: str, stable: str
) -> None:
    """Plotly mints a chart's uid from a random seed on every render."""
    node = _node(**{"clip-path": f'url("#{minted}")'})
    node["id"] = minted
    normalized = normalize._normalize(node)
    assert normalized["id"] == stable, (
        f"the uid should go from the id; got {normalized['id']!r}"
    )
    assert normalized["styleDiff"]["clip-path"] == f'url("#{stable}")', (
        f"and from the reference to it; got {normalized['styleDiff']!r}"
    )


def test_an_ordinary_id_survives_untouched() -> None:
    """Only Plotly's shape is incidental; anything else is the page's own."""
    for other in ("navbar", "clip-path-15", "eclipse2", "clipboard", "legend"):
        node = _node()
        node["id"] = other
        assert normalize._normalize(node)["id"] == other, (
            f"an ordinary id must survive untouched; {other!r} did not"
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
    inherited = {"color-scheme": "dark"}
    normalize._resolve_tracked({"color-scheme": "dark"}, inherited)

    assert inherited == {"color-scheme": "dark"}, (
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
    root = _node(**{"color-scheme": "dark"})
    child = _node(**{"color-scheme": "dark"})
    grandchild = _node(**{"color-scheme": "light dark"})
    child["children"] = [grandchild]
    root["children"] = [child]

    normalized = normalize._normalize(root)
    assert normalized["styleDiff"] == {"color-scheme": "dark"}, (
        f"the node that declares it should report it; got {normalized['styleDiff']!r}"
    )
    assert normalized["children"][0]["styleDiff"] == {}, (
        "a child inheriting the root's value is not declaring anything, and "
        "reporting it on every node buries the ones that differ; got "
        f"{normalized['children'][0]['styleDiff']!r}"
    )
    # A node that genuinely departs from its parent still reports.
    assert normalized["children"][0]["children"][0]["styleDiff"] == {
        "color-scheme": "light dark"
    }, (
        "de-duplicating against the parent must not silence a node that "
        "genuinely departs from it; got "
        f"{normalized['children'][0]['children'][0]['styleDiff']!r}"
    )


def test_the_members_only_one_tailwind_transitions_are_ignored() -> None:
    """v4's colour transition names outline-color and gradient stops; v3's did not."""
    v3 = _node(
        **{
            "transition-property": "color, background-color, border-color, "
            "text-decoration-color, fill, stroke, -webkit-text-decoration-color"
        }
    )
    v4 = _node(
        **{
            "transition-property": "color, background-color, border-color, "
            "outline-color, text-decoration-color, fill, stroke, "
            "--tw-gradient-from, --tw-gradient-via, --tw-gradient-to"
        }
    )
    assert (
        normalize._normalize(v3)["styleDiff"]["transition-property"]
        == normalize._normalize(v4)["styleDiff"]["transition-property"]
    ), "the two lists describe the same behaviour on this site"

    real = _node(**{"transition-property": "opacity"})
    assert (
        normalize._normalize(real)["styleDiff"]["transition-property"] == "opacity"
    ), "a transition both Tailwinds listed is a real declaration and survives"


@pytest.mark.parametrize(
    ("reported", "canonical"),
    [
        ("9999px", "9999px"),
        ("3.35544e+07px", "9999px"),
        ("1e+07px 3.35544e+07px", "9999px 9999px"),
        ("8px", "8px"),
        ("9998px", "9998px"),
    ],
)
def test_a_radius_past_a_semicircle_reads_as_the_same_radius(
    reported: str, canonical: str
) -> None:
    """`rounded-full` is 9999px in v3 and calc(infinity * 1px) in v4."""
    normalized = normalize._normalize(_node(**{"border-top-left-radius": reported}))
    assert normalized["styleDiff"]["border-top-left-radius"] == canonical, (
        "v3's 9999px and v4's infinite radius draw the same corner"
    )


def _stack(
    *margins: dict[str, str], parent: dict[str, str] | None = None
) -> dict[str, typ.Any]:
    """Build a parent whose children carry the given margins."""
    root = _node(**(parent or {}))
    root["children"] = [_node(**margin) for margin in margins]
    return root


def _gaps(tree: dict[str, typ.Any]) -> list[dict[str, str]]:
    """Read back each child's folded gaps and any margins left behind."""
    return [
        {
            k: v
            for k, v in child["styleDiff"].items()
            if k.startswith(("gap-", "margin-"))
        }
        for child in normalize._normalize(tree)["children"]
    ]


def test_space_y_reads_the_same_whichever_sibling_carries_the_margin() -> None:
    """v3 margined every child but the first; v4 every child but the last."""
    v3 = _stack({}, {"margin-top": "16px"}, {"margin-top": "16px"})
    v4 = _stack({"margin-bottom": "16px"}, {"margin-bottom": "16px"}, {})
    assert _gaps(v3) == _gaps(v4), (
        "the children sit in the same places, so their gaps must read the same"
    )
    assert _gaps(v3)[1]["gap-before-top"] == "16px", (
        "the space between the first two siblings is the margin that made it"
    )
    assert "gap-before-top" not in _gaps(v3)[0], "the first child has nothing before it"
    assert _gaps(v3)[0]["gap-after-bottom"] == "16px", "but 16px after it"
    assert "gap-after-bottom" not in _gaps(v3)[2], "and the last nothing after it"


def test_a_gap_on_the_parent_reads_the_same_as_margins_on_the_children() -> None:
    """`gap-x-4` on a flex row is what v4 recommends in place of `space-x-4`."""
    spaced = _stack({}, {"margin-left": "16px"}, {"margin-left": "16px"})
    gapped = _stack({}, {}, {}, parent={"column-gap": "16px"})
    assert _gaps(spaced) == _gaps(gapped), (
        "a gap on the parent and margins on the children put the siblings in "
        "the same places, so they fold to the same gaps"
    )
    assert "column-gap" not in normalize._normalize(gapped)["styleDiff"], (
        "the parent's gap is folded into the children's and must not also count"
    )


def test_a_margin_that_really_changes_still_changes_a_gap() -> None:
    """The folding must not swallow a real move."""
    before = _stack({}, {"margin-top": "16px"})
    after = _stack({}, {"margin-top": "24px"})
    assert _gaps(before) != _gaps(after), (
        "a margin that really changed must still change a gap, or the fold "
        "would hide a regression"
    )


def test_a_margin_that_is_not_a_length_is_left_alone() -> None:
    """`auto` centres a block; it is not a gap and is kept as a margin."""
    centred = _stack({"margin-left": "auto", "margin-right": "auto"})
    gaps = _gaps(centred)[0]
    assert gaps["margin-left"] == "auto", "an auto margin is centring, not a gap"
    assert "gap-before-left" not in gaps, "a child with an auto margin folds no gap"


@pytest.mark.parametrize("position", ["0px 0px", "0% 0%"])
def test_a_background_at_its_origin_is_where_an_unpositioned_one_is(
    position: str,
) -> None:
    """Chromium spells the default in percentages and a reset in pixels."""
    normalized = normalize._normalize(_node(**{"background-position": position}))
    assert "background-position" not in normalized["styleDiff"], (
        "a background at the origin is where an unpositioned one already sits"
    )

    moved = normalize._normalize(_node(**{"background-position": "50% 50%"}))
    assert moved["styleDiff"]["background-position"] == "50% 50%", (
        "a background moved off the origin is a real position"
    )


def test_a_light_colour_scheme_reads_as_the_default_one() -> None:
    """A page that only offers light renders the same either way."""
    light = normalize._normalize(_node(**{"color-scheme": "light"}))
    assert "color-scheme" not in light["styleDiff"], (
        "light is the default scheme; only v4 says so"
    )

    dark = normalize._normalize(_node(**{"color-scheme": "dark"}))
    assert dark["styleDiff"]["color-scheme"] == "dark", "dark is a real change"


def test_the_head_is_not_compared() -> None:
    """Nothing in the head renders, and a cutover's whole point is what it removes."""
    root = _node()
    root["tag"] = "html"
    head = _node()
    head["tag"] = "head"
    script = _node()
    script["tag"] = "script"
    head["children"] = [script]
    body = _node()
    body["tag"] = "body"
    root["children"] = [head, body]
    normalized = normalize._normalize(root)
    assert normalized["children"][0]["children"] == [], "the head's children go"
    assert normalized["children"][1]["tag"] == "body", "the body stays"


def test_a_class_list_is_not_compared() -> None:
    """A rename is the usual reason for a change that is meant to look the same."""
    node = _node(color="rgb(1, 2, 3)")
    node["classes"] = ["shadow-sm"]
    normalized = normalize._normalize(node)
    assert "classes" not in normalized, (
        "the class list is how a node is styled, not what it looks like"
    )
    assert normalized["styleDiff"]["color"] == "rgba(1, 2, 3, 1.000)", (
        "what the classes computed to is still compared"
    )


def test_a_parent_gap_stays_when_an_interior_auto_margin_blocks_a_boundary() -> None:
    """One boundary that cannot fold keeps the gap on the parent for all of them.

    With three children and `auto` on the middle one, the outer children can
    still fold their far boundaries, but the two boundaries that meet the
    middle child cannot be summed. Dropping the parent's gap then would hide
    a change to it on exactly those boundaries.
    """
    parent = {"row-gap": "16px"}
    children = [
        _node(**{"margin-top": "0px", "margin-bottom": "0px"}) for _ in range(3)
    ]
    children[1]["styleDiff"]["margin-top"] = "auto"
    folds._fold_sibling_margins(children, parent)
    assert parent["row-gap"] == "16px", (
        "the gap stays on the parent while any boundary is unrepresentable"
    )
    assert children[1]["styleDiff"]["margin-top"] == "auto", (
        "the auto margin is left as declared"
    )
    assert "gap-after-bottom" not in children[0]["styleDiff"], (
        "the boundary that meets the auto margin is not folded on either side"
    )
    assert children[2]["styleDiff"]["gap-before-top"] == "16px", (
        "the boundary the auto margin does not touch still folds, with the gap"
    )


class TestTransformFolding:
    """v4's individual transform properties fold to the matrix v3 wrote."""

    def test_a_v4_rotation_reads_as_the_matrix_v3_wrote(self) -> None:
        """`rotate-2` was a transform in v3 and is a `rotate` property in v4."""
        v3 = _node(transform="matrix(0.999391, 0.0348995, -0.0348995, 0.999391, 0, 0)")
        v4 = _node(rotate="2deg")
        assert (
            normalize._normalize(v3)["styleDiff"]["transform"]
            == normalize._normalize(v4)["styleDiff"]["transform"]
        ), "v3's composed matrix and v4's individual rotate must fold alike"
        assert "rotate" not in normalize._normalize(v4)["styleDiff"], (
            "v4's individual rotate is folded into the composed transform"
        )

    def test_a_v4_translation_resolves_against_the_box(self) -> None:
        """`-translate-x-1/2` is a percentage in v4 and was pixels in v3's matrix."""
        v3 = _node(transform="matrix(1, 0, 0, 1, -64, 0)")
        v4 = _node(translate="-50%")
        for node in (v3, v4):
            node["bbox"] = {"x": 0, "y": 0, "width": 128, "height": 40}
        assert (
            normalize._normalize(v3)["styleDiff"]["transform"]
            == normalize._normalize(v4)["styleDiff"]["transform"]
        ), "a percentage translation resolves against the box to v3's pixels"

    def test_an_identity_transform_is_left_unsaid(self) -> None:
        """v3's bare `transform` utility wrote an identity matrix; v4 writes none."""
        v3 = _node(transform="matrix(1, 0, 0, 1, 0, 0)")
        assert "transform" not in normalize._normalize(v3)["styleDiff"], (
            "an identity matrix is no transform at all and is left unsaid"
        )

    def test_a_real_transform_survives(self) -> None:
        """The folding must not swallow a transform that is not one of the pins."""
        moved = _node(transform="matrix(1, 0, 0, 1, 10, 0)")
        assert (
            normalize._normalize(moved)["styleDiff"]["transform"]
            == "matrix(1, 0, 0, 1, 10, 0)"
        )

    def test_an_undisplayed_node_has_no_transform_to_compare(self) -> None:
        """Chromium computes `transform` to none but keeps `rotate` as declared."""
        v3 = _node(display="none", transform="none")
        v4 = _node(display="none", rotate="2deg")
        assert (
            normalize._normalize(v3)["styleDiff"]
            == normalize._normalize(v4)["styleDiff"]
        )

    @pytest.mark.parametrize(
        ("key", "value"),
        [("scale", "1 1 2"), ("translate", "0px 0px 1px")],
        ids=["depth-scale", "depth-translate"],
    )
    def test_a_depth_component_is_not_folded_into_a_flat_matrix(
        self, key: str, value: str
    ) -> None:
        """A z component has no 2D matrix, so the properties stay as reported."""
        style = {key: value, "transform": "none"}
        transform._fold_transform(style, {"x": 0, "y": 0, "width": 10, "height": 10})
        assert style[key] == value, f"a non-default depth {key} must survive: {style!r}"
        assert style["transform"] == "none", "and the transform stays as it was"

    @pytest.mark.parametrize(
        ("key", "value"),
        [("scale", "2 2 1"), ("translate", "4px 0px 0px")],
        ids=["flat-scale", "flat-translate"],
    )
    def test_a_default_depth_component_still_folds(self, key: str, value: str) -> None:
        """Chromium reports the z component even when nothing set it."""
        style = {key: value}
        transform._fold_transform(style, {"x": 0, "y": 0, "width": 10, "height": 10})
        assert key not in style, (
            f"a default depth component folds like a 2D value: {style!r}"
        )
        assert style["transform"].startswith("matrix("), "and the matrix is composed"
