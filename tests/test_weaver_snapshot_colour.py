"""How the harness writes one colour, whatever notation the browser used.

Tailwind v3 resolved an opacity modifier to `rgba()`, v4 resolves it through
`color-mix()` in Oklab, and the theme is written in OKLCH. All three describe
the same pixels, so a diff must not report them as different — while still
reporting the colours that genuinely moved.
"""

from __future__ import annotations

import pytest

from tests.support.weaver_harness import load

colour = load("weaver_snapshot_colour")


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
    assert colour._canonical_value(notation) == expected, (
        f"{notation!r} should canonicalize to {expected!r}, so that two ways "
        f"of writing one colour compare equal; got "
        f"{colour._canonical_value(notation)!r}"
    )


def test_distinct_colours_stay_distinct() -> None:
    """Normalization must not collapse colours that genuinely differ.

    Tailwind v4 redefined its stock palette in OKLCH, so ``green-500`` moved
    from ``#22c55e`` to a slightly different green. That is a real change and
    the differ has to report it.
    """
    v3_green = colour._canonical_value("rgb(34, 197, 94)")
    v4_green = colour._canonical_value("oklch(0.723 0.219 149.579)")
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
    normalize = colour._canonical_shadow
    assert normalize(colour._canonical_value(v3)) == normalize(
        colour._canonical_value(v4)
    ), (
        "v3 and v4 pad a shadow with different numbers of transparent layers; "
        "dropping the layers that paint nothing is what makes the two equal"
    )
    assert normalize(colour._canonical_value(v3)) == (
        "rgba(0, 0, 0, 0.050) 0px 1px 2px 0px"
    ), (
        "only the placeholder layers should go; the one layer that actually "
        "paints must survive intact"
    )


def test_a_real_shadow_change_survives_normalization() -> None:
    """Dropping placeholders must not hide a shadow that actually moved."""
    normalize = colour._canonical_shadow
    two_px = normalize("rgba(25, 60, 110, 1.000) 2px 2px 0px 0px")
    four_px = normalize("rgba(25, 60, 110, 1.000) 4px 4px 0px 0px")
    assert two_px != four_px, (
        "dropping placeholder layers must not also hide a shadow that moved; "
        "2px and 4px offsets are a visible difference"
    )


def test_a_shadow_of_only_transparent_layers_becomes_none() -> None:
    """With nothing left to paint, the value is reported as `none`."""
    placeholder = "rgba(0, 0, 0, 0.000) 0px 0px 0px 0px"
    collapsed = colour._canonical_shadow(placeholder)
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
    dropped = colour._canonical_shadow(geometry)
    assert dropped == "none", (
        "a transparent layer paints nothing whatever its offset, blur or "
        f"spread, so it should be dropped; {geometry!r} gave {dropped!r}"
    )

    visible = "rgba(25, 60, 110, 0.100) 4px 4px 0px 0px"
    kept = colour._canonical_shadow(f"{geometry}, {visible}")
    assert kept == visible, (
        "dropping the transparent layer must leave the visible one intact; "
        f"expected {visible!r}, got {kept!r}"
    )


@pytest.mark.parametrize(
    ("percentage", "number"),
    [
        # 100% on the `a` and `b` axes is 0.4, not 1.0 — CSS Color 4. Reading
        # them as 1.0 put a percentage-written colour two and a half times too
        # far from grey.
        ("oklab(0.5 100% 0%)", "oklab(0.5 0.4 0)"),
        ("oklab(0.5 -100% 50%)", "oklab(0.5 -0.4 0.2)"),
        ("oklab(50% 25% -25%)", "oklab(0.5 0.1 -0.1)"),
        # Chroma takes the same scale; hue is an angle and never a percentage.
        ("oklch(0.5 100% 120)", "oklch(0.5 0.4 120)"),
        ("oklch(50% 50% 240)", "oklch(0.5 0.2 240)"),
    ],
)
def test_a_percentage_axis_means_what_the_specification_says(
    percentage: str, number: str
) -> None:
    """A colour written in percentages is the same colour written in numbers."""
    assert colour._canonical_value(percentage) == colour._canonical_value(number), (
        f"{percentage!r} and {number!r} are one colour written two ways, but "
        f"they canonicalize to {colour._canonical_value(percentage)!r} and "
        f"{colour._canonical_value(number)!r}"
    )


def test_a_percentage_lightness_still_maps_to_one() -> None:
    """Only the axes take the 0.4 scale; lightness keeps the ordinary mapping."""
    assert colour._canonical_value("oklch(100% 0 0)") == colour._canonical_value(
        "oklch(1 0 0)"
    ), "100% lightness is 1.0, and scaling it with the axes would darken white"


def test_an_opaque_layer_with_no_geometry_paints_nothing() -> None:
    """v3's ring composed a white zero-size offset layer; v4 composes none."""
    v3 = (
        "rgba(255, 255, 255, 1.000) 0px 0px 0px 0px, "
        "rgba(0, 0, 0, 0.050) 0px 0px 0px 1px"
    )
    v4 = "rgba(0, 0, 0, 0.050) 0px 0px 0px 1px"
    assert colour._canonical_shadow(v3) == colour._canonical_shadow(v4)
    assert colour._canonical_shadow(v4) == v4, "a drawn ring is kept"
