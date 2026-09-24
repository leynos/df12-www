"""Semantic snapshots of the Cuprum components that carry the design language.

``test_cuprum_build.py`` asserts invariants across every published page;
these snapshots pin the *structure* of one representative of each
component — the masthead, a route map, a code panel, an output block, the
home page's receipt, a flow figure, the capability matrix, a docs plate, the
docs navigation, one API entry, and a job sheet's facts table. A refactor
that keeps a class name but reshapes the tree, or drops ARIA wiring or a
``data-cu-*`` hook a script depends on, shows up here as a reviewable diff
instead of passing silently.

The serialization is deliberately semantic, not literal, so the snapshots
stay stable under copy edits and Cuprum releases:

- Text content is omitted entirely — prose changes are not regressions.
- The inside of ``pre`` and ``svg`` is omitted too: highlighted code is one
  ``span`` per token, so its shape follows the code rather than the
  component, and an icon's paths are artwork.
- Only structural attributes are kept (class, id, role, ``aria-*``,
  ``data-*``, href/src and their kin, and inline style), and their values
  pass through a redaction pass that masks volatile material: commit SHAs,
  source line anchors, version numbers, ISO dates, asset paths, image sizes,
  and the ``url(...)`` and ``aspect-ratio`` of a plate's inline style. Email
  addresses are masked as well, which keeps PII out of the snapshots by
  construction.

A diff is expected when a component's markup changes on purpose — a new
element, a renamed class, different ARIA wiring — and when the documented
Cuprum release changes the API entry's members. Review it, then regenerate
the snapshots under ``__snapshots__/`` with::

    uv run pytest tests/test_cuprum_snapshots.py --snapshot-update
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
PUBLIC_CUPRUM = REPO_ROOT / "public" / "cuprum"

#: How a target is found: the first element with a class token, carrying an
#: attribute, or with an id.
type _Match = tuple[typ.Literal["class", "attr", "id"], str]

#: One representative of each Cuprum component, by page and first match.
SNAPSHOT_TARGETS: dict[str, tuple[str, _Match]] = {
    "home-masthead": ("index.html", ("class", "cu-mast")),
    "home-receipt": ("index.html", ("class", "cu-receipt")),
    "first-command-routemap": (
        "examples/first-command/index.html",
        ("attr", "data-cu-routemap"),
    ),
    "first-command-code-panel": (
        "examples/first-command/index.html",
        ("class", "cu-code"),
    ),
    "first-command-output": (
        "examples/first-command/index.html",
        ("class", "cu-output"),
    ),
    "first-command-facts": (
        "examples/first-command/index.html",
        ("class", "cu-facts"),
    ),
    "getting-started-flow-figure": (
        "getting-started/index.html",
        ("class", "cu-figure"),
    ),
    "rust-extension-capability-matrix": (
        "internals/rust-extension/index.html",
        ("class", "cu-matrix-wrap"),
    ),
    "guide-output-plate": ("docs/guides/output/index.html", ("class", "cu-plate")),
    "guide-output-docs-nav": (
        "docs/guides/output/index.html",
        ("class", "cu-docs-nav"),
    ),
    "api-commands-safecmd": ("docs/api/commands/index.html", ("id", "SafeCmd")),
}

#: Attributes that describe structure or accessibility rather than content.
#: ``aria-*`` and ``data-*`` are kept as well; everything else is dropped.
_STRUCTURAL_ATTRS = frozenset(
    {
        "id",
        "role",
        "href",
        "src",
        "srcset",
        "sizes",
        "width",
        "height",
        "style",
        "type",
        "for",
        "name",
        "scope",
        "colspan",
        "rowspan",
        "headers",
        "popover",
        "popovertarget",
        "hidden",
        "open",
        "tabindex",
        "datetime",
    }
)

#: Attributes kept only to show they are present; their values are sizes.
_SIZE_ATTRS = frozenset({"sizes", "width", "height"})

#: Elements whose descendants are omitted from the outline.
_OPAQUE_ELEMENTS = frozenset({"pre", "svg"})

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
    (re.compile(r"url\([^)]*\)"), "url([path])"),
    (re.compile(r"aspect-ratio:\s*[^;]+"), "aspect-ratio: [ratio]"),
    (re.compile(r"/cuprum/assets/[^\s\"',)]+"), "[asset]"),
    (re.compile(r"\b\d+w\b"), "[w]"),
    (re.compile(r"#L\d+(?:-L\d+)?\b"), "#L[line]"),
    (re.compile(r"\b[0-9a-f]{7,40}\b"), "[sha]"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}(?:T[\d:.+Z-]+)?\b"), "[date]"),
    (
        re.compile(r"\bv?\d+\.\d+(?:\.\d+)*(?:[-.]?(?:a|b|rc|alpha|beta|dev)\d*)?\b"),
        "[version]",
    ),
)


def _redact(value: str) -> str:
    """Mask digests, line anchors, versions, dates, paths, and addresses."""
    for pattern, replacement in _REDACTIONS:
        value = pattern.sub(replacement, value)
    return value


def _kept(key: str) -> bool:
    """Report whether an attribute describes structure."""
    return key in _STRUCTURAL_ATTRS or key.startswith(("aria-", "data-"))


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
            key: "[size]" if key in _SIZE_ATTRS else _redact(value)
            for key, value in self.attrs.items()
            if _kept(key)
        }
        rendered = "".join(f" {key}={kept[key]!r}" for key in sorted(kept))
        lines = [f"{'  ' * depth}{self.tag}{classes}{rendered}"]
        for child in self.children:
            lines.extend(child.outline(depth + 1))
        return lines


def _matches(match: _Match, attributes: dict[str, str]) -> bool:
    """Report whether an element's attributes satisfy ``match``."""
    kind, value = match
    if kind == "class":
        return value in attributes.get("class", "").split()
    if kind == "attr":
        return value in attributes
    return attributes.get("id") == value


class _SubtreeParser(HTMLParser):
    """Extract the first element satisfying a match from a document."""

    def __init__(self, match: _Match) -> None:
        super().__init__(convert_charrefs=True)
        self._match = match
        self._stack: list[_Node] = []
        self._opaque_depth = 0
        self.root: _Node | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._opaque_depth:
            if tag not in _VOID_ELEMENTS:
                self._opaque_depth += 1
            return
        if self.root is not None and not self._stack:
            return  # already captured the first match
        attributes = {key: value or "" for key, value in attrs}
        capturing = bool(self._stack)
        starts_here = self.root is None and _matches(self._match, attributes)
        if not capturing and not starts_here:
            return
        node = _Node(tag, attributes)
        if capturing:
            self._stack[-1].children.append(node)
        else:
            self.root = node
        if tag not in _VOID_ELEMENTS:
            self._stack.append(node)
            if tag in _OPAQUE_ELEMENTS:
                self._opaque_depth = 1

    def handle_endtag(self, tag: str) -> None:
        if self._opaque_depth:
            if tag in _VOID_ELEMENTS:
                return  # a self-closed void element opened nothing
            self._opaque_depth -= 1
            if self._opaque_depth:
                return
        if self._stack and self._stack[-1].tag == tag:
            self._stack.pop()


def _component_outline(page: Path, match: _Match) -> str:
    """Serialize the first element in ``page`` satisfying ``match``."""
    parser = _SubtreeParser(match)
    parser.feed(page.read_text(encoding="utf-8"))
    assert parser.root is not None, (
        f"no element matching {match!r} in {page.relative_to(REPO_ROOT)}"
    )
    return "\n".join(parser.root.outline()) + "\n"


@pytest.mark.timeout(300)
@pytest.mark.parametrize(
    ("relative", "match"),
    SNAPSHOT_TARGETS.values(),
    ids=SNAPSHOT_TARGETS.keys(),
)
def test_cuprum_component_structure(
    built_site: Path,
    snapshot: SnapshotAssertion,
    relative: str,
    match: _Match,
) -> None:
    """Each component keeps its element tree, ARIA wiring, and script hooks."""
    assert built_site.is_dir()
    page = PUBLIC_CUPRUM / relative
    assert page.is_file(), f"expected a published page at {page}"
    assert _component_outline(page, match) == snapshot
