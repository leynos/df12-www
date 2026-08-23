"""Property-based tests for the Weaver snapshot normalization.

The example-based suite in ``tests/test_weaver_snapshot.py`` asserts what the
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
import importlib.util
import typing as typ
from pathlib import Path

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[1]

_SPEC = importlib.util.spec_from_file_location(
    "weaver_snapshot", REPO_ROOT / "scripts" / "weaver_snapshot.py"
)
assert _SPEC is not None, "scripts/weaver_snapshot.py could not be located"
assert _SPEC.loader is not None, (
    "spec for weaver_snapshot has no loader; it cannot be executed"
)
weaver_snapshot = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(weaver_snapshot)

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

TRACKED = sorted(weaver_snapshot._TRACKS_PARENT)

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
    once = weaver_snapshot._canonical_value(value)
    assert weaver_snapshot._canonical_value(once) == once, (
        f"{value!r} normalized to {once!r}, which normalizes again to "
        f"{weaver_snapshot._canonical_value(once)!r}"
    )


@given(shadows)
@SETTINGS
def test_canonicalizing_a_shadow_twice_changes_nothing(value: str) -> None:
    """A shadow with no fixed point would differ against an unchanged page."""
    once = weaver_snapshot._canonical_shadow(value)
    assert weaver_snapshot._canonical_shadow(once) == once, (
        f"{value!r} normalized to {once!r}, which normalizes again to "
        f"{weaver_snapshot._canonical_shadow(once)!r}"
    )


@given(shadows)
@SETTINGS
def test_no_transparent_layer_survives_normalization(value: str) -> None:
    """Alpha decides whether a layer paints, whatever geometry it carries."""
    canonical = weaver_snapshot._canonical_shadow(value)
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
    assert weaver_snapshot._canonical_value(red_green_blue) == (
        weaver_snapshot._canonical_value(opaque)
    ), f"{red_green_blue!r} and {opaque!r} are the same colour written twice"


@given(style_diffs())
@SETTINGS
def test_no_tailwind_internal_survives(style: dict[str, typ.Any]) -> None:
    """Which `--tw-*` variables exist is a Tailwind version detail."""
    normalized = weaver_snapshot._canonical_style(style)
    leaked = [key for key in normalized if key.startswith("--tw-")]
    assert not leaked, f"{leaked!r} survived normalization of {style!r}"


@given(style_diffs())
@SETTINGS
def test_canonical_style_never_invents_a_property(style: dict[str, typ.Any]) -> None:
    """Normalization removes; it must not add."""
    normalized = weaver_snapshot._canonical_style(style)
    assert set(normalized) <= set(style), (
        f"{set(normalized) - set(style)!r} appeared from nowhere"
    )


@given(nodes())
@SETTINGS
def test_normalizing_a_tree_twice_changes_nothing(node: dict[str, typ.Any]) -> None:
    """A snapshot is compared against a snapshot, so this must be a fixed point."""
    once = weaver_snapshot._normalize(node)
    assert weaver_snapshot._normalize(once) == once, (
        "normalization is not idempotent, so two captures of an unchanged page "
        "could differ"
    )


@given(nodes())
@SETTINGS
def test_normalization_preserves_the_shape_of_the_tree(
    node: dict[str, typ.Any],
) -> None:
    """Values are incidental; the document's structure is the thing compared."""
    assert _shape(weaver_snapshot._normalize(node)) == _shape(node), (
        "normalization added, dropped or reordered a node"
    )


@given(nodes())
@SETTINGS
def test_normalization_does_not_touch_its_argument(
    node: dict[str, typ.Any],
) -> None:
    """The parsed snapshot is shared, so normalizing must not reach back into it."""
    before = copy.deepcopy(node)
    weaver_snapshot._normalize(node)
    assert node == before, "normalization mutated the tree it was given"


@given(st.lists(st.text(alphabet="abc/", max_size=8), min_size=2, max_size=6))
@SETTINGS
def test_distinct_pages_never_share_a_snapshot_filename(pages: list[str]) -> None:
    """Two pages sharing a slug would silently overwrite each other's capture."""
    normalized = {page.strip("/") for page in pages}
    assume(len(normalized) == len(pages))
    slugs = [weaver_snapshot._slug(page) for page in pages]
    assert len(set(slugs)) == len(slugs), (
        f"{pages!r} collided on {slugs!r}; one capture would overwrite another"
    )
