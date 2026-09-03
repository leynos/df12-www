"""Reducing a captured tree to what a reader could actually see.

Removing what the browser reports but nobody perceives — Tailwind's internal
custom properties, a colour on an edge of zero width, a shadow layer that
paints nothing, a value a node merely inherited — so that what remains in a
diff is a change to the page.
"""

from __future__ import annotations

import collections.abc as cabc
import json
import math
import re
import typing as typ

from weaver_snapshot_colour import _canonical_shadow, _canonical_value

if typ.TYPE_CHECKING:
    from pathlib import Path

# The physical and logical names for each border edge, paired so a width can
# be looked up from a colour property and vice versa.
_BORDER_EDGES = (
    ("border-top", "border-block-start"),
    ("border-right", "border-inline-end"),
    ("border-bottom", "border-block-end"),
    ("border-left", "border-inline-start"),
)


_ZERO_WIDTHS = frozenset({"0px", "0", "medium"})


# The origin the harness serves on, port and all, as it appears inside a
# computed `url()`. Chromium resolves `background-image` against the document,
# so an inline `style="background-image: url(/netsuke/assets/x.jpg)"` is
# reported with the loopback port the capture happened to be given — a new
# one per run, since the default asks the kernel for a free port.
_LOOPBACK_ORIGIN = re.compile(r"http://127\.0\.0\.1:\d+")


# The uid Plotly mints for a chart on every render — six hex digits from a
# random seed — as it appears in the ids of the chart's clip paths, defs and
# legend, and in the `clip-path: url("#clip…")` that references them. The
# docs' security page draws one such chart, and each capture would otherwise
# report the whole chart as renamed.
_PLOTLY_UID = re.compile(r"\b(clip|topdefs-|defs-|legend)[0-9a-f]{6}")


# Members of a `transition-property` list that Tailwind v4 adds and v3 did
# not — v4's `transition-colors` names `outline-color` and the gradient stops,
# and its `transition-transform` names the individual transform properties.
# Nothing on the site transitions an outline, a gradient, or a bare
# `translate`, so the two lists describe the same behaviour; dropping the
# members from both sides lets them compare equal.
# `-webkit-text-decoration-color` is v3's prefixed duplicate of
# `text-decoration-color`.
_TRANSITION_NOISE = frozenset(
    {
        "outline-color",
        "--tw-gradient-from",
        "--tw-gradient-via",
        "--tw-gradient-to",
        "-webkit-text-decoration-color",
        "translate",
        "scale",
        "rotate",
    }
)


# A pixel length. Used to read margins and to cap radii.
_PX = re.compile(r"(-?\d+(?:\.\d+)?(?:e[+-]?\d+)?)px")


# The radius at which a corner is a semicircle whatever the box. Tailwind v3's
# `rounded-full` was `9999px`; v4's is `calc(infinity * 1px)`, which Chromium
# reports as `3.35544e+07px`. Both are "as round as it gets".
_FULL_RADIUS = 9999.0


# The ways Chromium spells a background at its origin.
_ORIGIN_POSITIONS = frozenset({"0px 0px", "0% 0%", "0px", "0%"})


# Properties a running animation samples mid-cycle. `opacity` is what a pulse
# changes; `transform` is what a spin changes, and it drags the node's
# bounding box round with it.
_ANIMATED = ("opacity", "transform")


def _drop_invisible_border_colours(style: dict[str, typ.Any]) -> None:
    """Remove the colour of any border edge that is not drawn.

    Tailwind v3's preflight defaulted every border to ``gray-200``; v4 leaves
    it at ``currentColor``. That changes the reported colour on roughly four
    and a half thousand nodes per page, of which only forty draw a border at
    all. Reporting the rest would bury the forty.

    Parameters
    ----------
    style
        A node's computed styles, modified in place.
    """
    for physical, logical in _BORDER_EDGES:
        width = style.get(f"{physical}-width", style.get(f"{logical}-width"))
        # A missing width means the walker saw the user-agent default, which
        # is zero for every element the preflight touches.
        if width is None or width in _ZERO_WIDTHS:
            style.pop(f"{physical}-color", None)
            style.pop(f"{logical}-color", None)


# Properties that take their value from the parent in practice, but which the
# walker compares against the user-agent default instead of against the
# parent. It therefore repeats them on every node in the subtree. `color-scheme`
# is inherited by specification; the rest default to `currentColor` and so
# follow `color` wherever it goes. Set once on `:root`, any of them would
# otherwise be reported five thousand times.
_TRACKS_PARENT = frozenset(
    {
        "color-scheme",
        "outline-color",
        "caret-color",
        "column-rule-color",
        "row-rule-color",
        "text-emphasis-color",
        "-webkit-text-fill-color",
        "-webkit-text-stroke-color",
    }
)


def _canonical_style(style_diff: dict[str, typ.Any] | None) -> dict[str, typ.Any]:
    """Strip incidental variation from one node's reported styles.

    Five kinds of variation are incidental:

    - Custom properties. ``--tw-*`` are Tailwind's own plumbing, and the
      theme tokens a compiled stylesheet declares on ``:root`` — several
      hundred of them — are what the visible properties are computed from,
      not something a reader can see; a token that changes shows up in every
      property that consumes it.
    - Colour notation. Tailwind v3 resolved `text-primary/80` to `rgba(...)`;
      v4 resolves it through `color-mix()` and Chromium reports `oklab(...)`.
      Comparing the strings would report every translucent colour on the site
      as changed and bury the handful that really did. Each colour is
      therefore converted to 8-bit sRGB before comparison, which is the
      precision a screen has anyway.
    - ``opacity`` and ``transform`` on a node running a CSS animation. The
      Weaver pages carry an ``animate-pulse`` status dot whose opacity is
      sampled mid-cycle; the Netsuke guides hub carries an ``animate-spin``
      icon whose rotation is.
    - The loopback port inside a ``url()``. The server is given a free port
      per run, and Chromium reports a resolved ``background-image`` with the
      origin it was loaded from.
    - Placeholder shadow layers. v4 composes ``box-shadow`` from more slots
      than v3 did, so an unchanged shadow arrives behind a different number of
      fully transparent, zero-size layers. See :func:`_canonical_shadow`.
    - The colour of a border edge with no width. See
      :func:`_drop_invisible_border_colours`.
    - The members of a ``transition-property`` list that only one Tailwind
      version names, and a corner radius past the point where the corner is
      a semicircle. See :func:`_canonical_transition` and
      :func:`_capped_radius`.
    - A background positioned at its origin, and ``color-scheme: light``,
      neither of which a light page renders any differently for.

    :func:`_normalize` handles three more that need the node rather than its
    styles alone: the individual transform properties are composed into the
    matrix (see :func:`_fold_transform`), the ``<head>`` is not compared, and
    neither is a node's class list.

    Parameters
    ----------
    style_diff
        The ``styleDiff`` a walker node reported, or ``None`` when it carried
        no styles of its own.

    Returns
    -------
    dict
        A fresh mapping with those variations removed. The argument is left
        alone.
    """
    style = {
        key: _incidental_text(_canonical_value(value))
        if isinstance(value, str)
        else value
        for key, value in (style_diff or {}).items()
        if not key.startswith("--")
    }
    if _is_animated(style):
        for key in _ANIMATED:
            style.pop(key, None)
    for key in ("box-shadow", "text-shadow"):
        if isinstance(style.get(key), str):
            style[key] = _canonical_shadow(style[key])
    # A background positioned at the origin is where an unpositioned one
    # already is; Chromium reports the one in pixels and the default in
    # percentages, and a `background:` shorthand in a layered rule resets it
    # to the former.
    if style.get("background-position") in _ORIGIN_POSITIONS:
        del style["background-position"]
    # A light page renders the same whether it declares `color-scheme: light`
    # or leaves it `normal`; the declaration only matters to a page that
    # also offers dark. daisyUI's theme declares it on the root.
    if style.get("color-scheme") in {"light", "normal"}:
        del style["color-scheme"]
    if isinstance(style.get("transition-property"), str):
        style["transition-property"] = _canonical_transition(
            style["transition-property"]
        )
    for key, value in style.items():
        if key.endswith("-radius") and isinstance(value, str):
            style[key] = _capped_radius(value)
    _drop_invisible_border_colours(style)
    return style


def _canonical_transition(value: str) -> str:
    """Drop the members of a transition list that only one Tailwind knew.

    Parameters
    ----------
    value
        A computed ``transition-property``.

    Returns
    -------
    str
        The list without the members in :data:`_TRANSITION_NOISE`.
    """
    kept = [part for part in value.split(", ") if part not in _TRANSITION_NOISE]
    return ", ".join(kept)


def _capped_radius(value: str) -> str:
    """Read any radius past a semicircle as the same radius.

    Parameters
    ----------
    value
        A computed ``border-*-radius``.

    Returns
    -------
    str
        The value with every pixel length at or beyond :data:`_FULL_RADIUS`
        replaced by it.
    """

    def cap(match: re.Match[str]) -> str:
        length = float(match.group(1))
        return f"{_FULL_RADIUS:g}px" if length >= _FULL_RADIUS else match.group(0)

    return _PX.sub(cap, value)


def _incidental_text(value: str) -> str:
    """Strip the run-to-run noise a string value can carry.

    Parameters
    ----------
    value
        A computed style value, or an id.

    Returns
    -------
    str
        The value with the loopback port and any Plotly uid removed.
    """
    return _PLOTLY_UID.sub(r"\1", _LOOPBACK_ORIGIN.sub("http://127.0.0.1", value))


def _is_animated(style: dict[str, typ.Any]) -> bool:
    """Say whether a node's styles show a CSS animation running on it."""
    return style.get("animation-name", "none") != "none"


def _resolve_tracked(
    style: dict[str, typ.Any],
    inherited: dict[str, typ.Any],
) -> dict[str, typ.Any]:
    """Drop the tracked properties a node merely repeats from its parent.

    The walker compares the properties in :data:`_TRACKS_PARENT` against the
    user-agent default rather than against the parent, so one declaration on
    ``:root`` is reported on every node beneath it. A node keeps such a
    property only where it genuinely departs from what it was handed, and the
    departure is what its own children are then compared against.

    Parameters
    ----------
    style
        The node's normalized styles, modified in place: any tracked property
        matching the inherited value is removed.
    inherited
        What the parent carried for those properties. Empty at the root.

    Returns
    -------
    dict
        The values to hand to this node's children, which is *inherited*
        updated with whatever this node overrode.
    """
    carried = dict(inherited)
    for key in _TRACKS_PARENT & style.keys():
        if style[key] == inherited.get(key):
            del style[key]
        else:
            carried[key] = style[key]
    return carried


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
    except (ValueError, IndexError):
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


def _translate_matrix(value: str, bbox: _Bbox) -> tuple[float, ...] | None:
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
    tx = _length(parts[0], float(bbox.get("width", 0)))
    ty = _length(parts[1], float(bbox.get("height", 0))) if len(parts) > 1 else 0.0
    if tx is None or ty is None:
        return None
    return (1.0, 0.0, 0.0, 1.0, tx, ty)


def _fold_transform(style: dict[str, typ.Any], bbox: _Bbox) -> None:
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
    if composed == _IDENTITY:
        style.pop("transform", None)
        return
    rounded = ", ".join(f"{round(part, _MATRIX_PLACES) + 0:g}" for part in composed)
    style["transform"] = f"matrix({rounded})"


# The physical margins, each with the logical name Chromium reports beside it
# in a left-to-right document, and the parent gap that sits on the same axis.
_MARGIN_AXES = (
    ("top", "bottom", "margin-block-start", "margin-block-end", "row-gap"),
    ("left", "right", "margin-inline-start", "margin-inline-end", "column-gap"),
)


def _pixels(value: str | None) -> float | None:
    """Read a computed length as pixels, or ``None`` if it is not one.

    Parameters
    ----------
    value
        A computed margin or gap, or ``None`` when the node did not report
        one — which under the preflight means zero, since every element the
        preflight touches reports its zeroed margin as a diff from the
        user-agent default.

    Returns
    -------
    float or None
        The length in pixels, or ``None`` for ``auto``, a percentage, or
        anything else that is not a bare pixel length.
    """
    if value is None or value == "normal":
        return 0.0
    match = _PX.fullmatch(value)
    return float(match.group(1)) if match else None


def _fold_sibling_margins(
    children: list[dict[str, typ.Any]], parent_style: dict[str, typ.Any]
) -> None:
    """Rewrite each child's margins as the gaps between it and its siblings.

    Tailwind v3's ``space-y-*`` put a top margin on every child but the first;
    v4 puts a bottom margin on every child but the last. The children sit in
    exactly the same places, and every one of them reports a different
    margin. The same holds for ``space-x-*``, and for a ``gap-*`` on the
    parent standing in for either. What a reader sees is the space between
    two siblings, so that is what is compared: a child's gap before it is its
    own leading margin plus the previous sibling's trailing one plus the
    parent's gap on that axis, and likewise after. A margin that really
    changes still changes a gap.

    Parameters
    ----------
    children
        A node's normalized children, modified in place. A child whose margin
        on an axis is not a pixel length — ``auto``, a percentage — keeps its
        margins on that axis as they were.
    parent_style
        The parent's normalized styles, from which any ``row-gap`` or
        ``column-gap`` is read and then removed.
    """
    for before, after, logical_before, logical_after, gap_key in _MARGIN_AXES:
        gap = _pixels(parent_style.pop(gap_key, None)) or 0.0
        leading = [
            _pixels(child["styleDiff"].get(f"margin-{before}")) for child in children
        ]
        trailing = [
            _pixels(child["styleDiff"].get(f"margin-{after}")) for child in children
        ]
        for index, child in enumerate(children):
            own_leading, own_trailing = leading[index], trailing[index]
            if own_leading is None or own_trailing is None:
                continue
            previous = trailing[index - 1] if index else 0.0
            following = leading[index + 1] if index + 1 < len(children) else 0.0
            if previous is None or following is None:
                continue
            style = child["styleDiff"]
            for key in (
                f"margin-{before}",
                f"margin-{after}",
                logical_before,
                logical_after,
            ):
                style.pop(key, None)
            gap_before = own_leading + previous + (gap if index else 0.0)
            gap_after = (
                own_trailing + following + (gap if index + 1 < len(children) else 0.0)
            )
            # A zero gap is what an absent margin already meant, so it is
            # left unsaid, as the margin would have been.
            if gap_before:
                style[f"gap-before-{before}"] = f"{gap_before:g}px"
            if gap_after:
                style[f"gap-after-{after}"] = f"{gap_after:g}px"


# Whatever the walker put in a node's `bbox`. It is a mapping today; the type
# says "some JSON value" because the normalization deliberately does not
# require that, and a snapshot reporting it otherwise should reach the diff
# rather than be dropped on the way.
type _Bbox = dict[str, typ.Any] | list[typ.Any] | str | float | bool | None


def _rounded_bbox(bbox: _Bbox) -> _Bbox:
    """Round a bounding box's numbers, absorbing subpixel text-shaping jitter.

    Two decimal places is finer than any layout shift worth reporting and
    coarser than the noise, so a real move still shows and a re-shaped glyph
    does not.

    Parameters
    ----------
    bbox
        A walker node's ``bbox``. Anything that is not a mapping is returned
        unchanged rather than discarded: the walker owns this field's shape,
        and a snapshot that starts reporting it differently should surface in
        the diff rather than be quietly dropped here.

    Returns
    -------
    dict or list or str or float or bool or None
        A fresh mapping with each numeric value rounded, or the argument
        itself when it is not a mapping.
    """
    if not isinstance(bbox, dict):
        return bbox
    return {
        key: round(value, 2) if isinstance(value, (int, float)) else value
        for key, value in bbox.items()
    }


def _normalize(
    node: dict[str, typ.Any],
    inherited: dict[str, typ.Any] | None = None,
    *,
    spinning: bool = False,
) -> dict[str, typ.Any]:
    """Strip incidental variation from one walker node and its descendants.

    The normalization itself lives in :func:`_canonical_style`,
    :func:`_resolve_tracked` and :func:`_rounded_bbox`; this function walks the
    tree and reassembles each node from their results.

    Parameters
    ----------
    node
        A walker-mode node, as emitted by ``css-view``.
    inherited
        The values the parent node carried for the properties in
        :data:`_TRACKS_PARENT`. Empty at the root.
    spinning
        Whether an ancestor is running an animation. Its box turns with it,
        and so does every box beneath it: the ``<path>`` inside a spinning
        icon has no animation of its own and moves all the same.

    Returns
    -------
    dict
        The node with those variations removed, and its children likewise. The
        argument is left alone.
    """
    style = _canonical_style(node.get("styleDiff"))
    carried = _resolve_tracked(style, inherited or {})

    spinning = spinning or _is_animated(style)
    _fold_transform(style, node.get("bbox"))
    normalized = dict(node)
    normalized["styleDiff"] = style
    # The class list is how a node is styled, not what it looks like, and a
    # rename is the usual reason for a change that is meant to look the same.
    # Only the computed result is compared, as the projection in AGENTS.md
    # does. The root's text is the head's — the title and any inline style —
    # and goes with the head.
    normalized.pop("classes", None)
    if node.get("tag") in {"html", "head"}:
        normalized.pop("text", None)
    if "bbox" in node:
        # A spinning node's box is whatever its rotation was when sampled;
        # rounding cannot settle that, so the box goes rather than the diff
        # reporting a spinner on every capture.
        if spinning:
            del normalized["bbox"]
        else:
            normalized["bbox"] = _rounded_bbox(node["bbox"])
    if isinstance(node.get("id"), str):
        normalized["id"] = _incidental_text(node["id"])
    # Nothing in the head is rendered, and the two <script> elements the
    # Play CDN needed are exactly what a cutover removes: the change is the
    # point, and reporting it on every page would bury whatever else moved.
    # A stylesheet that stopped being linked shows up in every style it set.
    children = [] if node.get("tag") == "head" else node.get("children") or []
    normalized["children"] = [
        _normalize(child, carried, spinning=spinning) for child in children
    ]
    _fold_sibling_margins(normalized["children"], style)
    return normalized


class _MalformedSnapshotError(ValueError):
    """A parsed snapshot that is not the shape ``css-view`` writes."""


def _check_node(node: typ.Any, where: str) -> None:  # noqa: ANN401 - the document is untyped upstream data
    """Check one walker node, and everything below it, is the shape assumed.

    The normalization reaches for ``.get`` on every node and ``.items`` on
    every ``styleDiff``, so anything that is not a mapping surfaces from deep
    inside the recursion as ``'str' object has no attribute 'get'`` — an
    ``AttributeError``, which the read boundary was not catching, naming
    neither the file nor the node. Walking the shape first means the failure
    can say where in the tree it is.

    Parameters
    ----------
    node
        The node to check.
    where
        A breadcrumb naming its position, such as ``payload.tree.children[2]``.

    Raises
    ------
    _MalformedSnapshotError
        If the node, its ``styleDiff``, or any descendant is not the shape the
        normalization assumes.
    """
    if not isinstance(node, cabc.Mapping):
        message = f"{where} is {type(node).__name__}, not a mapping"
        raise _MalformedSnapshotError(message)

    style = node.get("styleDiff")
    if style is not None and not isinstance(style, cabc.Mapping):
        message = (
            f"{where}.styleDiff is {type(style).__name__}, not a mapping or absent"
        )
        raise _MalformedSnapshotError(message)

    children = node.get("children")
    if children is None:
        return
    # A string is a Sequence, and iterating one yields characters rather than
    # nodes, so it has to be excluded by name.
    if isinstance(children, str) or not isinstance(children, cabc.Sequence):
        message = f"{where}.children is {type(children).__name__}, not a list or absent"
        raise _MalformedSnapshotError(message)
    for index, child in enumerate(children):
        _check_node(child, f"{where}.children[{index}]")
    # Explicit, to match the early return above: a node with no children and a
    # node whose children all check out leave this function the same way.
    return


def _rendered_tree(payload: dict[str, typ.Any]) -> str:
    """Render a parsed snapshot's tree as stable, comparable text.

    Kept free of I/O, so the normalization and its serialization can be
    exercised on a literal payload rather than a file on disk.

    Parameters
    ----------
    payload
        A parsed ``css-view`` snapshot document.

    Returns
    -------
    str
        Pretty-printed JSON with sorted keys, ready to hand to a line differ.
        The capture envelope — URL, timestamp, browser — is dropped, since it
        records when the snapshot was taken, not what the page looks like.

    Raises
    ------
    KeyError
        If the document has no ``payload.tree``. :func:`_normalized_tree`
        converts this into a ``SystemExit`` naming the file.
    TypeError
        If either level is not a mapping, for the same reason.
    _MalformedSnapshotError
        If the tree is not mappings all the way down, naming the node that is
        not. :func:`_normalized_tree` converts this the same way.
    """
    tree = payload["payload"]["tree"]
    _check_node(tree, "payload.tree")
    return json.dumps(_normalize(tree), indent=2, sort_keys=True, ensure_ascii=False)


def _normalized_tree(snapshot: Path) -> str:
    """Read a snapshot and render its tree as stable, comparable text.

    This is the I/O boundary. A snapshot directory is written by ``capture``
    but read here by path, so it can be stale, truncated by an interrupted
    run, or simply not a snapshot at all. Each of those surfaces as a
    ``SystemExit`` naming the file rather than as a traceback partway through
    a comparison, where the file at fault is the one thing not on screen.

    Parameters
    ----------
    snapshot
        Path to a ``css-view`` JSON snapshot.

    Returns
    -------
    str
        The rendering :func:`_rendered_tree` produces.

    Raises
    ------
    SystemExit
        If the file cannot be read, does not hold valid JSON, or does not have
        the shape ``css-view`` writes.
    """
    try:
        text = snapshot.read_text(encoding="utf-8")
    except OSError as exc:
        message = f"{snapshot} could not be read ({exc})"
        raise SystemExit(message) from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        message = (
            f"{snapshot} is not valid JSON ({exc}); an interrupted capture "
            f"can leave a partial file behind, so recapture it"
        )
        raise SystemExit(message) from exc
    try:
        return _rendered_tree(payload)
    except (KeyError, TypeError) as exc:
        message = (
            f"{snapshot} has no payload.tree, so it is not a css-view "
            f"snapshot ({exc!r})"
        )
        raise SystemExit(message) from exc
    except _MalformedSnapshotError as exc:
        message = (
            f"{snapshot} is not the shape css-view writes: {exc}. An "
            f"interrupted capture, or a snapshot from a different tool, would "
            f"look like this; recapture it."
        )
        raise SystemExit(message) from exc
