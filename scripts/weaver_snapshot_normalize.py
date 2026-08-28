"""Reducing a captured tree to what a reader could actually see.

Removing what the browser reports but nobody perceives — Tailwind's internal
custom properties, a colour on an edge of zero width, a shadow layer that
paints nothing, a value a node merely inherited — so that what remains in a
diff is a change to the page.
"""

from __future__ import annotations

import collections.abc as cabc
import json
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

    - ``--tw-*`` custom properties. These are Tailwind's own plumbing, and
      which of them exist is an implementation detail of the version in use,
      not something a reader can see.
    - Colour notation. Tailwind v3 resolved `text-primary/80` to `rgba(...)`;
      v4 resolves it through `color-mix()` and Chromium reports `oklab(...)`.
      Comparing the strings would report every translucent colour on the site
      as changed and bury the handful that really did. Each colour is
      therefore converted to 8-bit sRGB before comparison, which is the
      precision a screen has anyway.
    - ``opacity`` on a node running a CSS animation. The Weaver pages carry an
      ``animate-pulse`` status dot whose opacity is sampled mid-cycle.
    - Placeholder shadow layers. v4 composes ``box-shadow`` from more slots
      than v3 did, so an unchanged shadow arrives behind a different number of
      fully transparent, zero-size layers. See :func:`_canonical_shadow`.
    - The colour of a border edge with no width. See
      :func:`_drop_invisible_border_colours`.

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
        key: _canonical_value(value) if isinstance(value, str) else value
        for key, value in (style_diff or {}).items()
        if not key.startswith("--tw-")
    }
    if style.get("animation-name", "none") != "none":
        style.pop("opacity", None)
    for key in ("box-shadow", "text-shadow"):
        if isinstance(style.get(key), str):
            style[key] = _canonical_shadow(style[key])
    _drop_invisible_border_colours(style)
    return style


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

    Returns
    -------
    dict
        The node with those variations removed, and its children likewise. The
        argument is left alone.
    """
    style = _canonical_style(node.get("styleDiff"))
    carried = _resolve_tracked(style, inherited or {})

    normalized = dict(node)
    normalized["styleDiff"] = style
    if "bbox" in node:
        normalized["bbox"] = _rounded_bbox(node["bbox"])
    normalized["children"] = [
        _normalize(child, carried) for child in node.get("children") or []
    ]
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
