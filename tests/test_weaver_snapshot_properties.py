"""Property-based tests for the Weaver snapshot normalization.

The example-based suites in ``tests/test_weaver_snapshot_*.py`` assert what the
normalization does to the inputs someone thought of. These assert what must
hold for every input, which is a different question and catches a different
class of defect — the colour notation nobody anticipated, the tree shape the
walker has not produced yet, the value that normalizes differently the second
time it is seen.

Three properties carry most of the weight:

- **Idempotence.** Normalizing an already-normalized value must change
  nothing. A snapshot is compared against another snapshot, so a normalizer
  with no fixed point would report a difference between two captures of an
  unchanged page.
- **Structure preservation.** Normalization removes incidental *values*; it
  must never add, drop or reorder a node. A comparison is only meaningful if
  both trees still describe the same document.
- **Removal is total.** Every ``--tw-*`` property goes, and no transparent
  shadow layer survives, whatever else is in the value.
"""

from __future__ import annotations

import copy
import math
import typing as typ
from pathlib import Path

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from tests.support.weaver_harness import load

REPO_ROOT = Path(__file__).resolve().parents[1]

# The normalization now spans two modules: the colour canonicalization these
# properties feed, and the tree walk that applies it.
colour = load("weaver_snapshot_colour")
normalize = load("weaver_snapshot_normalize")
paths = load("weaver_snapshot_paths")

# Deterministic and quiet: these run in the commit gate, so a flaky example or
# a slow-data health check would be a gate failure rather than a finding.
SETTINGS = settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)

channels = st.integers(min_value=0, max_value=255)
alphas = st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False)
lengths = st.integers(min_value=-64, max_value=64).map(lambda n: f"{n}px")


@st.composite
def colours(draw: st.DrawFn) -> str:
    """Emit a colour in one of the notations Chromium reports."""
    red, green, blue = (draw(channels) for _ in range(3))
    notation = draw(st.sampled_from(["rgb", "rgba", "hex", "keyword"]))
    if notation == "rgb":
        return f"rgb({red}, {green}, {blue})"
    if notation == "rgba":
        return f"rgba({red}, {green}, {blue}, {draw(alphas):.3f})"
    if notation == "hex":
        return f"#{red:02x}{green:02x}{blue:02x}"
    return draw(st.sampled_from(["currentColor", "transparent", "none", "inherit"]))


@st.composite
def shadow_layers(draw: st.DrawFn) -> str:
    """Emit one shadow layer, transparent about half the time."""
    red, green, blue = (draw(channels) for _ in range(3))
    alpha = draw(st.sampled_from([0.0, draw(alphas)]))
    geometry = " ".join(draw(lengths) for _ in range(4))
    return f"rgba({red}, {green}, {blue}, {alpha:.3f}) {geometry}"


shadows = st.lists(shadow_layers(), min_size=1, max_size=4).map(", ".join)

TRACKED = sorted(normalize._TRACKS_PARENT)

# Deep enough for the inherited-property tracking to have something to
# carry down, shallow enough that a 200-example run stays quick.
MAX_TREE_DEPTH = 3

style_keys = st.one_of(
    st.sampled_from(TRACKED),
    st.sampled_from(
        [
            "color",
            "background-color",
            "opacity",
            "animation-name",
            "display",
            "border-top-width",
            "border-top-color",
            "border-left-width",
            "border-left-color",
        ]
    ),
    st.sampled_from(["--tw-ring-color", "--tw-shadow", "--tw-text-opacity"]),
)


@st.composite
def style_diffs(draw: st.DrawFn) -> dict[str, typ.Any]:
    """Emit a plausible ``styleDiff`` mapping."""
    style: dict[str, typ.Any] = {}
    for key in draw(st.lists(style_keys, max_size=8, unique=True)):
        if key.endswith("width"):
            style[key] = draw(st.sampled_from(["0px", "0", "medium", "2px"]))
        elif key == "animation-name":
            style[key] = draw(st.sampled_from(["none", "pulse"]))
        elif key == "opacity":
            style[key] = f"{draw(alphas):.6f}"
        elif key == "display":
            style[key] = draw(st.sampled_from(["flex", "block", "none"]))
        else:
            style[key] = draw(colours())
    for key in draw(
        st.lists(st.sampled_from(["box-shadow", "text-shadow"]), max_size=2)
    ):
        style[key] = draw(shadows)
    return style


@st.composite
def nodes(draw: st.DrawFn, depth: int = 0) -> dict[str, typ.Any]:
    """Emit a walker node, recursively, with the odd shapes the walker allows."""
    node: dict[str, typ.Any] = {"tag": "div", "classes": []}
    if draw(st.booleans()):
        node["styleDiff"] = draw(style_diffs())
    elif draw(st.booleans()):
        node["styleDiff"] = None
    if draw(st.booleans()):
        node["bbox"] = draw(
            st.one_of(
                st.fixed_dictionaries(
                    {
                        "x": st.floats(0, 4000, allow_nan=False),
                        "y": st.floats(0, 4000, allow_nan=False),
                        "width": st.floats(0, 4000, allow_nan=False),
                        "height": st.floats(0, 4000, allow_nan=False),
                    }
                ),
                st.none(),
                st.text(max_size=8),
                st.lists(st.integers(), max_size=4),
            )
        )
    children = (
        0 if depth >= MAX_TREE_DEPTH else draw(st.integers(min_value=0, max_value=2))
    )
    node["children"] = [draw(nodes(depth + 1)) for _ in range(children)]
    return node


type Shape = tuple[str | None, list["Shape"]]


def _shape(node: dict[str, typ.Any]) -> Shape:
    """Reduce a tree to its structure, ignoring every value that normalizes."""
    return (node.get("tag"), [_shape(child) for child in node.get("children") or []])


@given(colours())
@SETTINGS
def test_canonicalizing_a_value_twice_changes_nothing(value: str) -> None:
    """Comparing two snapshots means comparing two normalized values."""
    once = colour._canonical_value(value)
    assert colour._canonical_value(once) == once, (
        f"{value!r} normalized to {once!r}, which normalizes again to "
        f"{colour._canonical_value(once)!r}"
    )


@given(shadows)
@SETTINGS
def test_canonicalizing_a_shadow_twice_changes_nothing(value: str) -> None:
    """A shadow with no fixed point would differ against an unchanged page."""
    once = colour._canonical_shadow(value)
    assert colour._canonical_shadow(once) == once, (
        f"{value!r} normalized to {once!r}, which normalizes again to "
        f"{colour._canonical_shadow(once)!r}"
    )


@given(shadows)
@SETTINGS
def test_no_transparent_layer_survives_normalization(value: str) -> None:
    """Alpha decides whether a layer paints, whatever geometry it carries."""
    canonical = colour._canonical_shadow(value)
    assume(canonical != "none")
    assert ", 0.000)" not in canonical, (
        f"{value!r} normalized to {canonical!r}, which still paints nothing"
    )


@given(colours())
@SETTINGS
def test_two_notations_of_one_colour_normalize_alike(red_green_blue: str) -> None:
    """The point of canonicalizing at all: notation is not a difference."""
    assume(red_green_blue.startswith("rgb("))
    channels_only = red_green_blue.removeprefix("rgb(").removesuffix(")")
    opaque = f"rgba({channels_only}, 1.000)"
    assert colour._canonical_value(red_green_blue) == (
        colour._canonical_value(opaque)
    ), f"{red_green_blue!r} and {opaque!r} are the same colour written twice"


@given(style_diffs())
@SETTINGS
def test_no_tailwind_internal_survives(style: dict[str, typ.Any]) -> None:
    """Which `--tw-*` variables exist is a Tailwind version detail."""
    normalized = normalize._canonical_style(style)
    leaked = [key for key in normalized if key.startswith("--tw-")]
    assert not leaked, f"{leaked!r} survived normalization of {style!r}"


@given(style_diffs())
@SETTINGS
def test_canonical_style_never_invents_a_property(style: dict[str, typ.Any]) -> None:
    """Normalization removes; it must not add."""
    normalized = normalize._canonical_style(style)
    assert set(normalized) <= set(style), (
        f"{set(normalized) - set(style)!r} appeared from nowhere"
    )


@given(nodes())
@SETTINGS
def test_normalizing_a_tree_twice_changes_nothing(node: dict[str, typ.Any]) -> None:
    """A snapshot is compared against a snapshot, so this must be a fixed point."""
    once = normalize._normalize(node)
    assert normalize._normalize(once) == once, (
        "normalization is not idempotent, so two captures of an unchanged page "
        "could differ"
    )


@given(nodes())
@SETTINGS
def test_normalization_preserves_the_shape_of_the_tree(
    node: dict[str, typ.Any],
) -> None:
    """Values are incidental; the document's structure is the thing compared."""
    assert _shape(normalize._normalize(node)) == _shape(node), (
        "normalization added, dropped or reordered a node"
    )


@given(nodes())
@SETTINGS
def test_normalization_does_not_touch_its_argument(
    node: dict[str, typ.Any],
) -> None:
    """The parsed snapshot is shared, so normalizing must not reach back into it."""
    before = copy.deepcopy(node)
    normalize._normalize(node)
    assert node == before, "normalization mutated the tree it was given"


# `_` earns its place in the alphabet: the slug uses `__` as its separator, so
# a page whose directory name contains an underscore is exactly the input that
# can collide with a nested one. `abc/` alone never generates that case, and a
# strategy that cannot produce the collision cannot rule it out.
#
# The two literals cover the other way a stem can be claimed twice: the home
# page has a sentinel stem, and a real page at that path would collide with it.
page_paths = st.one_of(
    st.text(alphabet="abc/_", max_size=8),
    st.sampled_from(["home", "__home", "_uhome"]),
)


@given(st.lists(page_paths, min_size=2, max_size=6))
@SETTINGS
def test_distinct_pages_never_share_a_snapshot_filename(pages: list[str]) -> None:
    """Two pages sharing a slug would silently overwrite each other's capture."""
    normalized = {page.strip("/") for page in pages}
    assume(len(normalized) == len(pages))
    slugs = [paths._slug(page) for page in pages]
    assert len(set(slugs)) == len(slugs), (
        f"{pages!r} collided on {slugs!r}; one capture would overwrite another"
    )


# --- The v4 notation folds -------------------------------------------------
#
# Tailwind v4 reports the same rendering in a different notation: a
# transition list with members v3 never named, individual `rotate` and
# `translate` properties instead of a composed `transform`, a bottom margin
# where v3 put a top one. Each fold must be total, must be a fixed point, and
# must leave a genuine difference visible.

NOISE = sorted(normalize._TRANSITION_NOISE)
SIGNAL = ["color", "background-color", "border-color", "opacity", "transform"]
transition_lists = st.lists(
    st.sampled_from([*NOISE, *SIGNAL]), min_size=1, max_size=8
).map(", ".join)


@given(transition_lists)
@SETTINGS
def test_transition_noise_is_removed_and_the_rest_kept_in_order(value: str) -> None:
    """The members only one Tailwind knew go; the others keep their order."""
    canonical = normalize._canonical_transition(value)
    kept = [part for part in canonical.split(", ") if part]
    assert not set(kept) & set(NOISE), (
        f"a transition member v3 never listed survived: {canonical!r}"
    )
    assert kept == [part for part in value.split(", ") if part not in NOISE], (
        f"the members that stay must keep their order; {value!r} became {canonical!r}"
    )
    assert normalize._canonical_transition(canonical) == canonical, (
        f"canonicalizing a transition twice changed it: {canonical!r}"
    )


radius_lengths = st.floats(min_value=0, max_value=20000, allow_nan=False).map(
    lambda n: f"{n:g}px"
)
radii = st.lists(radius_lengths, min_size=1, max_size=4).map(" ".join)


@given(radii)
@SETTINGS
def test_no_radius_past_a_semicircle_survives_and_none_below_changes(
    value: str,
) -> None:
    """``rounded-full`` is 9999px in v3 and infinity in v4: the same corner."""
    capped = normalize._capped_radius(value)
    lengths = [float(part[:-2]) for part in capped.split()]
    assert all(length <= normalize._FULL_RADIUS for length in lengths), (
        f"a radius beyond the cap survived: {capped!r}"
    )
    for before, after in zip(value.split(), capped.split(), strict=True):
        if float(before[:-2]) < normalize._FULL_RADIUS:
            assert before == after, f"a radius below the cap changed: {before!r}"
    assert normalize._capped_radius(capped) == capped, (
        f"capping a radius twice changed it: {capped!r}"
    )


ports = st.integers(min_value=1, max_value=65535)
hex6 = st.from_regex(r"\A[0-9a-f]{6}\Z")
plain_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")), max_size=24
).filter(lambda text: "127.0.0.1:" not in text and "clip" not in text)


@given(plain_text, ports, hex6, st.sampled_from(["clip", "legend", "defs-"]))
@SETTINGS
def test_a_port_and_a_plotly_uid_are_incidental_whatever_they_are(
    text: str, port: int, uid: str, prefix: str
) -> None:
    """Both change every run without the page changing."""
    value = f"url(http://127.0.0.1:{port}/x.png) {text} url(#{prefix}{uid})"
    stripped = normalize._incidental_text(value)
    assert f":{port}" not in stripped.replace(text, ""), (
        f"the loopback port survived: {stripped!r}"
    )
    assert uid not in stripped.replace(text, ""), (
        f"the Plotly uid survived: {stripped!r}"
    )
    assert stripped == f"url(http://127.0.0.1/x.png) {text} url(#{prefix})", (
        f"more than the port and the uid changed: {stripped!r}"
    )
    assert normalize._incidental_text(stripped) == stripped, (
        f"stripping a value twice changed it: {stripped!r}"
    )


@given(plain_text)
@SETTINGS
def test_text_without_a_port_or_a_uid_is_left_alone(text: str) -> None:
    """The strip must not reach anything that is not run-to-run noise."""
    assert normalize._incidental_text(text) == text


factors = st.floats(min_value=0.1, max_value=4, allow_nan=False).map(
    lambda n: round(n, 3)
)
degrees = st.integers(min_value=-360, max_value=360)
# Close enough to the identity that the fold is expected to say nothing.
IDENTITY_TOLERANCE = 1e-9
offsets = st.integers(min_value=-200, max_value=200)


def _expected(sx: float, sy: float, angle: int, tx: int, ty: int) -> tuple[float, ...]:
    """Compose translate ∘ rotate ∘ scale by hand, the way the spec orders them."""
    cos, sin = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return (cos * sx, sin * sx, -sin * sy, cos * sy, float(tx), float(ty))


@given(factors, factors, degrees, offsets, offsets)
@SETTINGS
def test_individual_transforms_fold_to_the_matrix_v3_would_have_reported(
    sx: float, sy: float, angle: int, tx: int, ty: int
) -> None:
    """v4's ``scale``/``rotate``/``translate`` and v3's one matrix agree."""
    bbox = {"x": 0, "y": 0, "width": 100, "height": 50}
    v4 = {
        "scale": f"{sx:g} {sy:g}",
        "rotate": f"{angle}deg",
        "translate": f"{tx}px {ty}px",
    }
    normalize._fold_transform(v4, bbox)
    assert not {"scale", "rotate", "translate"} & v4.keys(), (
        f"an individual transform property survived the fold: {v4!r}"
    )
    expected = _expected(sx, sy, angle, tx, ty)
    rounded = ", ".join(
        f"{round(part, normalize._MATRIX_PLACES) + 0:g}" for part in expected
    )
    v3 = {"transform": f"matrix({rounded})"}
    normalize._fold_transform(v3, bbox)
    if all(
        abs(part - identity) < IDENTITY_TOLERANCE
        for part, identity in zip(expected, normalize._IDENTITY, strict=True)
    ):
        assert "transform" not in v4, f"an identity transform was reported: {v4!r}"
    else:
        assert v4 == v3, (
            f"the folded v4 properties {v4!r} disagree with v3's matrix {v3!r}"
        )
    again = dict(v4)
    normalize._fold_transform(again, bbox)
    assert again == v4, f"folding a transform twice changed it: {again!r}"


@given(factors, degrees, st.sampled_from(["none", "block", "flex"]))
@SETTINGS
def test_a_hidden_node_keeps_no_transform_at_all(
    sx: float, angle: int, display: str
) -> None:
    """Chromium leaves ``rotate`` as declared on a node it does not lay out."""
    style = {"display": display, "scale": f"{sx:g}", "rotate": f"{angle}deg"}
    normalize._fold_transform(style, {"width": 10, "height": 10})
    if display == "none":
        assert style == {"display": "none"}, (
            f"a hidden node carried a transform into the comparison: {style!r}"
        )
    else:
        assert "rotate" not in style, f"rotate survived on a laid-out node: {style!r}"
        assert "scale" not in style, f"scale survived on a laid-out node: {style!r}"


margins = st.integers(min_value=0, max_value=48).map(lambda n: f"{n}px")


def _child(top: str, bottom: str) -> dict[str, typ.Any]:
    return {
        "tag": "div",
        "styleDiff": {"margin-top": top, "margin-bottom": bottom},
        "children": [],
    }


@given(
    st.lists(st.tuples(margins, margins), min_size=1, max_size=6),
    st.one_of(st.none(), margins),
)
@SETTINGS
def test_moving_a_margin_across_a_sibling_boundary_leaves_the_gaps_alone(
    pairs: list[tuple[str, str]], gap: str | None
) -> None:
    """v3's ``space-y`` and v4's are the same layout, and must fold the same.

    v3 puts the space on the top of every child but the first; v4 on the
    bottom of every child but the last. Shift every trailing margin onto the
    next child's leading edge and the folded gaps must not change.
    """
    parent = {} if gap is None else {"row-gap": gap}
    v4 = [_child(top, bottom) for top, bottom in pairs]
    v3 = [_child(top, bottom) for top, bottom in pairs]
    for index in range(len(v3) - 1):
        moved = int(v3[index]["styleDiff"]["margin-bottom"][:-2])
        v3[index]["styleDiff"]["margin-bottom"] = "0px"
        leading = int(v3[index + 1]["styleDiff"]["margin-top"][:-2])
        v3[index + 1]["styleDiff"]["margin-top"] = f"{leading + moved}px"
    normalize._fold_sibling_margins(v4, dict(parent))
    normalize._fold_sibling_margins(v3, dict(parent))
    assert [child["styleDiff"] for child in v4] == [
        child["styleDiff"] for child in v3
    ], "the same space between two siblings folded to different gaps"
    for child in v4:
        assert not {"margin-top", "margin-bottom"} & child["styleDiff"].keys(), (
            f"a margin survived the fold: {child['styleDiff']!r}"
        )


@given(st.lists(st.tuples(margins, margins), min_size=2, max_size=6), margins)
@SETTINGS
def test_each_gap_is_the_two_margins_that_meet_plus_the_parent_gap(
    pairs: list[tuple[str, str]], gap: str
) -> None:
    """What a reader sees between two siblings is exactly this sum."""
    children = [_child(top, bottom) for top, bottom in pairs]
    normalize._fold_sibling_margins(children, {"row-gap": gap})
    for index in range(1, len(children)):
        expected = (
            int(pairs[index][0][:-2]) + int(pairs[index - 1][1][:-2]) + int(gap[:-2])
        )
        reported = children[index]["styleDiff"].get("gap-before-top", "0px")
        assert reported == f"{expected}px", (
            f"child {index} reports {reported} before it; expected {expected}px"
        )


@given(st.lists(st.tuples(margins, margins), min_size=1, max_size=4), margins)
@SETTINGS
def test_a_child_with_an_auto_margin_keeps_its_margins(
    pairs: list[tuple[str, str]], gap: str
) -> None:
    """``mx-auto`` centring is not a gap and must survive as declared."""
    children = [_child(top, bottom) for top, bottom in pairs]
    children[0]["styleDiff"]["margin-top"] = "auto"
    normalize._fold_sibling_margins(children, {"row-gap": gap})
    assert children[0]["styleDiff"]["margin-top"] == "auto", (
        f"an auto margin was folded away: {children[0]['styleDiff']!r}"
    )
