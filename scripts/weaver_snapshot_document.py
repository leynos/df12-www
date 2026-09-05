"""Reading a snapshot from disk and rendering its normalized tree.

The shape check refuses a document that is not what the walker writes, and
the rendering is the text the diff compares: one normalized tree, laid out
deterministically.
"""

from __future__ import annotations

import json
import typing as typ

from weaver_snapshot_normalize import _normalize

if typ.TYPE_CHECKING:
    from pathlib import Path

    from weaver_snapshot_types import Json, WalkerNode


class SnapshotError(Exception):
    """Something about a snapshot the harness cannot work with."""


class MalformedSnapshotError(SnapshotError):
    """A parsed snapshot that is not the shape the walker writes.

    Attributes
    ----------
    where
        A breadcrumb naming the node at fault, such as
        ``payload.tree.children[2].styleDiff``.
    expected
        What the harness assumes is there, in words.
    actual
        The type name of what was found instead.
    """

    def __init__(self, where: str, expected: str, actual: str) -> None:
        self.where = where
        self.expected = expected
        self.actual = actual
        super().__init__(f"{where} is {actual}, not {expected}")


def _check_node(node: Json, where: str) -> None:
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
    MalformedSnapshotError
        If the node, its ``styleDiff``, or any descendant is not the shape the
        normalization assumes.
    """
    if not isinstance(node, dict):
        raise MalformedSnapshotError(where, "a mapping", type(node).__name__)

    style = node.get("styleDiff")
    if style is not None and not isinstance(style, dict):
        raise MalformedSnapshotError(
            f"{where}.styleDiff", "a mapping or absent", type(style).__name__
        )

    children = node.get("children")
    if children is None:
        return
    # A string is a Sequence, and iterating one yields characters rather than
    # nodes, so it has to be excluded by name.
    if not isinstance(children, list):
        raise MalformedSnapshotError(
            f"{where}.children", "a list or absent", type(children).__name__
        )
    for index, child in enumerate(children):
        _check_node(child, f"{where}.children[{index}]")
    # Explicit, to match the early return above: a node with no children and a
    # node whose children all check out leave this function the same way.
    return


def _rendered_tree(payload: Json) -> str:
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
    inner = payload.get("payload") if isinstance(payload, dict) else None
    if not isinstance(inner, dict):
        # Whatever the document is, it has no `payload.tree` to check.
        raise MalformedSnapshotError("payload.tree", "a mapping", "absent")
    tree = inner.get("tree")
    _check_node(tree, "payload.tree")
    normalized = _normalize(typ.cast("WalkerNode", tree))
    return json.dumps(normalized, indent=2, sort_keys=True, ensure_ascii=False)


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
    except MalformedSnapshotError as exc:
        message = (
            f"{snapshot} is not the shape css-view writes: {exc}. An "
            f"interrupted capture, or a snapshot from a different tool, would "
            f"look like this; recapture it."
        )
        raise SystemExit(message) from exc
