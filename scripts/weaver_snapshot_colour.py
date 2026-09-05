"""Writing one colour one way, whatever notation the browser reported it in.

Tailwind v3 resolved an opacity modifier to `rgba()`; v4 resolves it through
`color-mix()` in Oklab, and the theme itself is written in OKLCH. All three
describe the same pixels, and a diff that reported them as different would
bury the changes that are real.
"""

from __future__ import annotations

import math
import re

# The sRGB transfer function's linear-segment cutoff, from the sRGB
# specification. Named so the conversion below does not read as a magic
# number.
SRGB_LINEAR_CUTOFF = 0.0031308


# Every colour notation handled here takes three components before the
# optional alpha.
COLOUR_COMPONENTS = 3

# What 100% means for Oklab's `a` and `b` axes, and for OKLCH's chroma, per
# CSS Color 4. Lightness uses the ordinary 0-1 mapping and hue is an angle.
OKLAB_AXIS_SCALE = 0.4


def _srgb_channel(value: float) -> int:
    """Convert one linear-light channel to an 8-bit sRGB value.

    Parameters
    ----------
    value
        A linear-light channel, nominally in ``[0, 1]`` but allowed to fall
        outside it for colours beyond the sRGB gamut.

    Returns
    -------
    int
        The gamma-encoded channel, clamped to ``[0, 255]``.
    """
    encoded = (
        12.92 * value
        if value <= SRGB_LINEAR_CUTOFF
        else 1.055 * (abs(value) ** (1 / 2.4)) - 0.055
    )
    return max(0, min(255, round(encoded * 255)))


def _oklab_to_rgb(lightness: float, a: float, b: float) -> tuple[int, int, int]:
    """Convert an Oklab colour to 8-bit sRGB.

    Parameters
    ----------
    lightness
        The Oklab ``L`` component, nominally in ``[0, 1]``.
    a, b
        The Oklab opponent components.

    Returns
    -------
    tuple of int
        Red, green, and blue, each in ``[0, 255]``.
    """
    long_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    medium = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    short = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (
        _srgb_channel(
            4.0767416621 * long_ - 3.3077115913 * medium + 0.2309699292 * short
        ),
        _srgb_channel(
            -1.2684380046 * long_ + 2.6097574011 * medium - 0.3413193965 * short
        ),
        _srgb_channel(
            -0.0041960863 * long_ - 0.7034186147 * medium + 1.7076147010 * short
        ),
    )


# Matches the colour notations Chromium reports in computed values. Tailwind
# v3 resolved an opacity modifier to `rgba(...)`; v4 resolves it through
# `color-mix()` in Oklab and reports `oklab(...)`. The colours are the same to
# within a rounding step, but the strings share not one character.
_COLOUR_FUNCTION = re.compile(
    r"\b(rgba?|oklab|oklch)\(\s*([^)]*)\)",
    re.IGNORECASE,
)


_NUMBER = re.compile(r"-?\d*\.?\d+(?:e-?\d+)?%?")


def _canonical_colour(match: re.Match[str]) -> str:
    """Rewrite one colour function as a canonical 8-bit ``rgba()`` string.

    Parameters
    ----------
    match
        A match of :data:`_COLOUR_FUNCTION`.

    Returns
    -------
    str
        ``rgba(r, g, b, a)`` with integer channels and alpha to three decimal
        places, or the original text if the arguments cannot be read.
    """
    name = match.group(1).lower()
    numbers = _NUMBER.findall(match.group(2))
    if len(numbers) < COLOUR_COMPONENTS:
        return match.group(0)

    def value(index: int, scale: float = 1.0) -> float:
        raw = numbers[index]
        return float(raw.rstrip("%")) / 100 * scale if raw.endswith("%") else float(raw)

    alpha = value(COLOUR_COMPONENTS) if len(numbers) > COLOUR_COMPONENTS else 1.0

    if name.startswith("rgb"):
        red, green, blue = (round(value(i, 255.0)) for i in range(COLOUR_COMPONENTS))
    elif name == "oklab":
        # CSS Color 4 scales a percentage differently per component: for
        # lightness 100% is 1.0, but for `a` and `b` 100% is 0.4 (and -100% is
        # -0.4). Reading them all as 1.0 would put a percentage-written colour
        # two and a half times too far from grey.
        red, green, blue = _oklab_to_rgb(
            value(0), value(1, OKLAB_AXIS_SCALE), value(2, OKLAB_AXIS_SCALE)
        )
    else:  # oklch
        # Chroma takes the same 0.4 scale as `a` and `b`; hue is an angle and
        # is never a percentage.
        chroma, hue = value(1, OKLAB_AXIS_SCALE), math.radians(value(2))
        red, green, blue = _oklab_to_rgb(
            value(0), chroma * math.cos(hue), chroma * math.sin(hue)
        )

    return f"rgba({red}, {green}, {blue}, {alpha:.3f})"


def _canonical_value(value: str) -> str:
    """Rewrite every colour function inside one computed value.

    Values such as ``box-shadow`` embed a colour among other components, so
    the substitution is applied in place rather than to the whole string.

    Parameters
    ----------
    value
        A computed property value.

    Returns
    -------
    str
        The value with each colour function in canonical ``rgba()`` form.
    """
    return _COLOUR_FUNCTION.sub(_canonical_colour, value)


# A shadow layer that paints nothing: fully transparent, no offset, no blur,
# no spread. Tailwind composes box-shadow from several `--tw-*` variables and
# v4 uses more of them than v3 did, so the same visible shadow arrives with a
# different number of these placeholders in front of it.
_EMPTY_SHADOW = "rgba(0, 0, 0, 0.000) 0px 0px 0px 0px"


# The alpha channel of a canonicalized `rgba()`, which `_canonical_colour` has
# already normalized to three decimal places by the time this runs.
_SHADOW_ALPHA = re.compile(r"rgba\([^)]*,\s*0\.000\s*\)")


# A layer with no geometry at all: no offset, no blur, no spread. Whatever its
# colour, it covers nothing. Tailwind v3's ring composed one in for the ring
# offset, in white, where v4 composes none.
_NO_GEOMETRY = re.compile(r"\)\s+0px 0px 0px 0px(?:\s+inset)?$")


def _is_transparent_shadow(layer: str) -> bool:
    """Report whether a shadow layer paints nothing.

    Alpha decides this on its own, and so does geometry. Matching the
    fully-zero placeholder by its exact text missed any transparent layer that
    carried a geometry — an offset, a blur, a spread — even though a shadow at
    alpha zero is invisible whatever its dimensions; and it missed an opaque
    layer with no geometry, which covers nothing whatever its colour. Two
    snapshots then differed over a layer neither of them drew.

    Parameters
    ----------
    layer
        One comma-separated layer of a canonicalized shadow value.

    Returns
    -------
    bool
        True when the layer is fully transparent and so paints nothing.
    """
    return (
        layer == _EMPTY_SHADOW
        or bool(_SHADOW_ALPHA.search(layer))
        or bool(_NO_GEOMETRY.search(layer))
    )


def _canonical_shadow(value: str) -> str:
    """Drop the placeholder layers from a composed ``box-shadow``.

    Parameters
    ----------
    value
        A canonicalized ``box-shadow`` value.

    Returns
    -------
    str
        The value with every layer that paints nothing removed, or ``"none"``
        if no layer survives.
    """
    # Split on top-level commas only: the layers themselves contain commas,
    # inside their rgba() colour.
    layers: list[str] = []
    buffer = ""
    depth = 0
    for char in value:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            layers.append(buffer.strip())
            buffer = ""
        else:
            buffer += char
    if buffer.strip():
        layers.append(buffer.strip())

    painted = [layer for layer in layers if not _is_transparent_shadow(layer)]
    return ", ".join(painted) if painted else "none"
