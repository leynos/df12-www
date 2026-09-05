"""Reducing a captured tree to what a reader could actually see.

Removing what the browser reports but nobody perceives — Tailwind's internal
custom properties, a colour on an edge of zero width, a shadow layer that
paints nothing, a value a node merely inherited — so that what remains in a
diff is a change to the page.
"""

from __future__ import annotations

import typing as typ

from weaver_snapshot_colour import _canonical_shadow, _canonical_value
from weaver_snapshot_folds import (
    _canonical_transition,
    _capped_radius,
    _fold_sibling_margins,
    _incidental_text,
)
from weaver_snapshot_transform import _Bbox, _fold_transform

# The physical and logical names for each border edge, paired so a width can
# be looked up from a colour property and vice versa.
_BORDER_EDGES = (
    ("border-top", "border-block-start"),
    ("border-right", "border-inline-end"),
    ("border-bottom", "border-block-end"),
    ("border-left", "border-inline-start"),
)
_ZERO_WIDTHS = frozenset({"0px", "0", "medium"})
# The ways Chromium spells a background at its origin.
_ORIGIN_POSITIONS = frozenset({"0px 0px", "0% 0%", "0px", "0%"})
# A running animation samples `opacity` mid-cycle, and a moving one samples
# `transform` and drags the node's bounding box round with it. A computed
# style names the animation but not what it animates, so the ones that move
# are named here: Tailwind's three transform animations. A pulse, or a border
# that cycles its colour, leaves its box where it is, and the box stays in
# the comparison.
_MOVING_ANIMATIONS = frozenset({"spin", "ping", "bounce"})


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
        style.pop("opacity", None)
    if _is_moving(style):
        style.pop("transform", None)
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


def _is_animated(style: dict[str, typ.Any]) -> bool:
    """Say whether a node's styles show a CSS animation running on it."""
    return style.get("animation-name", "none") != "none"


def _is_moving(style: dict[str, typ.Any]) -> bool:
    """Say whether a node is running an animation that moves its box."""
    names = str(style.get("animation-name", "none")).split(", ")
    return any(name in _MOVING_ANIMATIONS for name in names)


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
        Whether an ancestor is running an animation that moves it. Its box
        turns with it, and so does every box beneath it: the ``<path>``
        inside a spinning icon has no animation of its own and moves all the
        same. An animation that only cycles a colour or an opacity leaves
        every box in place, and those stay in the comparison.

    Returns
    -------
    dict
        The node with those variations removed, and its children likewise. The
        argument is left alone.
    """
    style = _canonical_style(node.get("styleDiff"))
    carried = _resolve_tracked(style, inherited or {})

    spinning = spinning or _is_moving(style)
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
