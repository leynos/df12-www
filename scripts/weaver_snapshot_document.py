"""Reading a snapshot from disk and rendering its normalized tree.

The shape check refuses a document that is not what the walker writes, and
the rendering is the text the diff compares: one normalized tree, laid out
deterministically.
"""

from __future__ import annotations

import collections.abc as cabc
import json
import typing as typ

from weaver_snapshot_normalize import _normalize

if typ.TYPE_CHECKING:
    from pathlib import Path


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
