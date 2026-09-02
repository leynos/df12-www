"""Semantic snapshots of the Stilyagi components the migration renamed.

``test_stilyagi_build.py`` asserts the renamed classes exist in published
markup; these snapshots pin the *structure around* them — the element tree,
class lists, and ARIA wiring of each renamed component and of one panel
from each ground (paper and ink). A refactor that keeps a class name but
drops the ARIA relationships or reshapes the tree shows up here as a
reviewable diff instead of passing silently.

The serialization is deliberately semantic, not literal, so the snapshots
stay stable under copy edits:

- Text content is omitted entirely — prose changes are not regressions.
- Only structural attributes are kept (class, id, role, ``aria-*``,
  popover wiring, href/src and their kin), and their values pass through
  a redaction pass that masks volatile material: hex digests, version
  numbers, ISO dates, and email addresses. Published Stilyagi pages carry
  none of those today, but the masking keeps a future addition from
  making the snapshots brittle — and keeps PII out of them by
  construction.

Snapshots live under ``__snapshots__/`` and are regenerated with
``uv run pytest tests/test_stilyagi_snapshots.py --snapshot-update``.
"""

from __future__ import annotations

import dataclasses as dc
import re
import typing as typ
from html.parser import HTMLParser
from pathlib import Path

import pytest

if typ.TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_STILYAGI = REPO_ROOT / "public" / "stilyagi"

#: One representative of each renamed component, plus one panel per ground:
#: ``tenet-card`` sits on paper and ``personas`` on ink, so between them the
#: pair exercises both sides of the ``--color-accent-text`` re-point.
SNAPSHOT_TARGETS = {
    "roadmap-slice-timeline": ("roadmap/index.html", "slice-timeline"),
    "roadmap-pacing-card": ("roadmap/index.html", "pacing-card"),
    "why-tenet-card": ("why/index.html", "tenet-card"),
    "why-personas-ink-panel": ("why/index.html", "personas"),
    "design-adr-status": ("design/index.html", "adr-status"),
    "docs-syntax-tabs": ("docs/index.html", "syntax-tabs"),
    "how-term-ink-panel": ("how/index.html", "term"),
}

#: Attributes that describe structure or accessibility rather than content.
#: Everything else (inline styles, data payloads, copy-bearing titles) is
#: dropped from the serialization.
_STRUCTURAL_ATTRS = frozenset(
    {
        "id",
        "role",
        "href",
        "src",
        "type",
        "for",
        "name",
        "popover",
        "popovertarget",
        "hidden",
        "tabindex",
        "datetime",
    }
)

_VOID_ELEMENTS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "source",
        "track",
        "wbr",
    }
)

#: Volatile material masked out of attribute values, most specific first.
#: Emails never appear in this markup, but masking them keeps PII out of
#: the snapshot files by construction rather than by inspection.
_REDACTIONS = (
    (re.compile(r"[^\s\"'@/]+@[^\s\"'@/]+\.[a-zA-Z]{2,}"), "[email]"),
    (re.compile(r"\b[0-9a-f]{7,40}\b"), "[sha]"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}(?:T[\d:.+Z-]+)?\b"), "[date]"),
    (re.compile(r"\bv?\d+\.\d+(?:\.\d+)*\b"), "[version]"),
)


def _redact(value: str) -> str:
    """Mask digests, versions, dates, and addresses in ``value``."""
    for pattern, replacement in _REDACTIONS:
        value = pattern.sub(replacement, value)
    return value


@dc.dataclass
class _Node:
    """One element in the parsed subtree."""

    tag: str
    attrs: dict[str, str]
    children: list[_Node] = dc.field(default_factory=list)

    def outline(self, depth: int = 0) -> list[str]:
        """Render the subtree as one indented line per element."""
        classes = "".join(f".{c}" for c in sorted(self.attrs.get("class", "").split()))
        kept = {
            key: _redact(value)
            for key, value in self.attrs.items()
            if key in _STRUCTURAL_ATTRS or key.startswith("aria-")
        }
        rendered = "".join(f" {key}={kept[key]!r}" for key in sorted(kept))
        lines = [f"{'  ' * depth}{self.tag}{classes}{rendered}"]
        for child in self.children:
            lines.extend(child.outline(depth + 1))
        return lines


class _SubtreeParser(HTMLParser):
    """Extract the first element carrying a class token from a document."""

    def __init__(self, wanted_class: str) -> None:
        super().__init__(convert_charrefs=True)
        self._wanted = wanted_class
        self._stack: list[_Node] = []
        self.root: _Node | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.root is not None and not self._stack:
            return  # already captured the first match
        attributes = {key: value or "" for key, value in attrs}
        capturing = bool(self._stack)
        starts_here = (
            self.root is None and self._wanted in attributes.get("class", "").split()
        )
        if not capturing and not starts_here:
            return
        node = _Node(tag, attributes)
        if capturing:
            self._stack[-1].children.append(node)
        else:
            self.root = node
        if tag not in _VOID_ELEMENTS:
            self._stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        if self._stack and self._stack[-1].tag == tag:
            self._stack.pop()


def _component_outline(page: Path, wanted_class: str) -> str:
    """Serialize the first ``wanted_class`` element in ``page`` semantically."""
    parser = _SubtreeParser(wanted_class)
    parser.feed(page.read_text(encoding="utf-8"))
    assert parser.root is not None, (
        f"no element with class {wanted_class!r} in {page.relative_to(REPO_ROOT)}"
    )
    return "\n".join(parser.root.outline()) + "\n"


@pytest.mark.timeout(300)
@pytest.mark.parametrize(
    ("relative", "wanted_class"),
    SNAPSHOT_TARGETS.values(),
    ids=SNAPSHOT_TARGETS.keys(),
)
def test_stilyagi_component_structure(
    built_site: Path,
    snapshot: SnapshotAssertion,
    relative: str,
    wanted_class: str,
) -> None:
    """Each renamed component keeps its element tree and ARIA wiring."""
    page = PUBLIC_STILYAGI / relative
    assert page.is_file(), f"expected a published page at {page}"
    assert _component_outline(page, wanted_class) == snapshot
