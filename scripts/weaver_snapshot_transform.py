"""Composing v4's individual transform properties into one matrix.

Tailwind v3 wrote ``rotate-2`` and ``-translate-x-1/2`` into ``transform``;
v4 writes them to the ``rotate`` and ``translate`` properties, which
Chromium reports separately. The element ends up in the same place, so the
comparison is made on the composed matrix.
"""

from __future__ import annotations

import math
import re
import typing as typ

from weaver_snapshot_folds import _pixels

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from weaver_snapshot_types import Json, Style

# A 2D transform matrix as Chromium reports it: six numbers, in the order
# `matrix(a, b, c, d, e, f)`.
_MATRIX = re.compile(r"matrix\(([^)]*)\)")

# The four decimal places a transform is compared at. Chromium reports a
# rotation's sine and cosine to six or seven, and the seventh differs between
# a matrix it composed and one this harness composes from `rotate`.
_MATRIX_PLACES = 4


def _matrix(value: str) -> tuple[float, ...] | None:
    """Read a computed transform as six numbers, or ``None`` if it is not one.

    Parameters
    ----------
    value
        A computed ``transform``.

    Returns
    -------
    tuple of float or None
        ``(a, b, c, d, e, f)`` for a 2D matrix; ``None`` for ``none``, a 3D
        matrix, or anything else.
    """
    match = _MATRIX.fullmatch(value.strip())
    if match is None:
        return None
    parts = [part.strip() for part in match.group(1).split(",")]
    if len(parts) != 6:  # noqa: PLR2004 - a 2D matrix has six numbers
        return None
    try:
        return tuple(float(part) for part in parts)
    except ValueError:
        return None


def _multiply(left: tuple[float, ...], right: tuple[float, ...]) -> tuple[float, ...]:
    """Compose two 2D matrices, applying *right* first."""
    a1, b1, c1, d1, e1, f1 = left
    a2, b2, c2, d2, e2, f2 = right
    return (
        a1 * a2 + c1 * b2,
        b1 * a2 + d1 * b2,
        a1 * c2 + c1 * d2,
        b1 * c2 + d1 * d2,
        a1 * e2 + c1 * f2 + e1,
        b1 * e2 + d1 * f2 + f1,
    )


def _length(value: str, extent: float) -> float | None:
    """Read a translation component as pixels, resolving a percentage."""
    if value.endswith("%"):
        try:
            return float(value[:-1]) / 100 * extent
        except ValueError:
            return None
    return _pixels(value)


_IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _scale_matrix(value: str) -> tuple[float, ...] | None:
    """Read a computed ``scale`` as a matrix, or ``None`` if it cannot be."""
    factors = value.split()
    try:
        sx = float(factors[0])
        sy = float(factors[1]) if len(factors) > 1 else sx
        sz = float(factors[2]) if len(factors) > 2 else 1.0  # noqa: PLR2004 - x, y, z
    except (ValueError, IndexError):
        return None
    # A depth scale has no 2D matrix; only the default one folds.
    if sz != 1.0:
        return None
    return (sx, 0.0, 0.0, sy, 0.0, 0.0)


def _rotate_matrix(value: str) -> tuple[float, ...] | None:
    """Read a computed ``rotate`` in degrees as a matrix, or ``None``."""
    if not value.endswith("deg"):
        return None
    try:
        angle = math.radians(float(value[:-3]))
    except ValueError:
        return None
    cos, sin = math.cos(angle), math.sin(angle)
    return (cos, sin, -sin, cos, 0.0, 0.0)


def _extent(value: Json) -> float:
    """Read a bounding-box dimension as a number, or zero if it is not one."""
    return float(value) if isinstance(value, (int, float)) else 0.0


def _translate_matrix(value: str, bbox: Json) -> tuple[float, ...] | None:
    """Read a computed ``translate`` as a matrix, resolving percentages.

    Parameters
    ----------
    value
        The computed ``translate``: one or two lengths or percentages.
    bbox
        The node's bounding box, against which a percentage resolves. A node
        without one cannot resolve a percentage, and ``None`` is returned.

    Returns
    -------
    tuple of float or None
        The translation as a matrix, or ``None`` if it cannot be read.
    """
    if not isinstance(bbox, dict):
        return None
    parts = value.split()
    if not parts:
        return None
    width, height = _extent(bbox.get("width")), _extent(bbox.get("height"))
    tx = _length(parts[0], width)
    ty = _length(parts[1], height) if len(parts) > 1 else 0.0
    tz = _pixels(parts[2]) if len(parts) > 2 else 0.0  # noqa: PLR2004 - x, y, z
    # A depth translation has no 2D matrix; only the default one folds.
    if tx is None or ty is None or tz != 0.0:
        return None
    return (1.0, 0.0, 0.0, 1.0, tx, ty)


def _fold_transform(style: Style, bbox: Json) -> None:
    """Compose the individual transform properties into ``transform``.

    Tailwind v3 wrote ``rotate-2`` and ``-translate-x-1/2`` into
    ``transform``; v4 writes them to the ``rotate`` and ``translate``
    properties, which Chromium reports separately and applies before
    ``transform``. The element ends up in the same place, so the comparison
    is made on the composed matrix — translate, then rotate, then scale, then
    the transform itself, per the specification — rounded to the places at
    which a rotation Chromium composed and one this harness composes agree.
    A value that cannot be read leaves every one of the four as reported.

    Parameters
    ----------
    style
        A node's normalized styles, modified in place.
    bbox
        The node's bounding box, against which a percentage translation
        resolves.
    """
    # An element that is not displayed has no box to transform. Chromium
    # computes its `transform` to `none` but leaves `rotate` and `translate`
    # as declared, so v3 and v4 would disagree over a node nobody can see.
    if style.get("display") == "none":
        for key in ("transform", "rotate", "translate", "scale"):
            style.pop(key, None)
        return
    transform = style.get("transform", "none")
    if not isinstance(transform, str):
        return
    composed = _IDENTITY if transform == "none" else _matrix(transform)
    if composed is None:
        return
    readers: list[tuple[str, cabc.Callable[[str], tuple[float, ...] | None]]] = [
        ("scale", _scale_matrix),
        ("rotate", _rotate_matrix),
        ("translate", lambda value: _translate_matrix(value, bbox)),
    ]
    for key, read in readers:
        value = style.get(key, "none")
        if not isinstance(value, str) or value == "none":
            continue
        part = read(value)
        if part is None:
            return
        composed = _multiply(part, composed)
    for key in ("rotate", "translate", "scale"):
        style.pop(key, None)
    # Compare after rounding: a full turn composes to a sine of 1e-16, which
    # is the identity to any reader and to the four places the harness keeps.
    rounded = tuple(round(part, _MATRIX_PLACES) + 0 for part in composed)
    if rounded == _IDENTITY:
        style.pop("transform", None)
        return
    style["transform"] = f"matrix({', '.join(f'{part:g}' for part in rounded)})"
