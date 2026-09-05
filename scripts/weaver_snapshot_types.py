"""The shapes the snapshot harness passes between its modules.

A snapshot is JSON the walker wrote inside a browser, read back by path. The
types here say what the harness assumes about it — no more, since a snapshot
that is not this shape must reach the shape check and be named there rather
than be refused by a type on the way in.
"""

from __future__ import annotations

import typing as typ

# Any JSON value. A snapshot is read with `json.loads`, and this is what it
# can hold.
type Json = dict[str, "Json"] | list["Json"] | str | int | float | bool | None

# A node's computed styles, raw from the walker or after canonicalization:
# property name to value. Values are strings in practice, but the walker is
# not trusted for that until the shape check has run.
type Style = dict[str, Json]


class WalkerNode(typ.TypedDict, total=False):
    """One element as the walker reports it, and as the normalization leaves it.

    Every key is optional: the walker writes them all, but the normalization
    drops some (``classes``, a spinning node's ``bbox``) and tolerates a
    snapshot that never had others. What it does assume — that ``styleDiff``
    is a mapping or absent and ``children`` a list or absent — is checked
    before a node reaches it.
    """

    tag: str
    id: str | None
    classes: list[str]
    role: str | None
    name: str | None
    text: str | None
    bbox: Json
    styleDiff: Style | None
    children: list[WalkerNode]
