"""No published Weaver page pulses its words.

``animate-pulse`` fades an element to half opacity and back every two seconds.
On a dot that is harmless, but on a word it takes the contrast down with it.
The "● LIVE" label on the how-it-works page fell from 5.55:1 to 2.28:1 on
every cycle, and the axe audit passed or failed by when it happened to sample
(#182). A pulse belongs on a mark beside the words, never on the words.

This is checked in the built markup, not in a browser, so it cannot depend on
the moment it looks.
"""

from __future__ import annotations

import typing as typ
from html.parser import HTMLParser

import pytest

if typ.TYPE_CHECKING:
    from pathlib import Path

# Elements that never hold content, so never have an end tag to close them.
VOID = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "source", "track", "wbr",
})  # fmt: skip


def _pulses(class_attribute: str | None) -> bool:
    """Say whether a class list animates with ``pulse``, under any variant."""
    return any(
        name.rsplit(":", 1)[-1] == "animate-pulse"
        for name in (class_attribute or "").split()
    )


class _PulsingText(HTMLParser):
    """Collect the text inside every element that pulses."""

    def __init__(self) -> None:
        """Start with no element open and no pulsing text found."""
        super().__init__()
        self._open: list[tuple[str, bool, list[str]]] = []
        self.found: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Track an element, noting whether it pulses."""
        if tag not in VOID:
            self._open.append((tag, _pulses(dict(attrs).get("class")), []))

    def handle_endtag(self, tag: str) -> None:
        """Close elements up to ``tag``, passing their text to the parent."""
        while self._open:
            name, pulses, text = self._open.pop()
            words = "".join(text).strip()
            if pulses and words:
                self.found.append(words)
            if self._open:
                self._open[-1][2].append("".join(text))
            if name == tag:
                return

    def handle_data(self, data: str) -> None:
        """Attribute text to the innermost open element."""
        if self._open:
            self._open[-1][2].append(data)


@pytest.mark.timeout(300)
def test_no_weaver_page_pulses_text(built_site: Path) -> None:
    """Every pulsing element on a Weaver page is a mark with no text in it."""
    offenders: dict[str, list[str]] = {}
    for page in sorted(built_site.rglob("*.html")):
        parser = _PulsingText()
        parser.feed(page.read_text(encoding="utf-8"))
        if parser.found:
            offenders[str(page.relative_to(built_site))] = parser.found
    assert not offenders, f"these Weaver pages pulse text: {offenders}"


@pytest.mark.parametrize(
    ("markup", "expected"),
    [
        ('<span class="animate-pulse">● LIVE</span>', ["● LIVE"]),
        ('<span class="motion-safe:animate-pulse">LIVE</span>', ["LIVE"]),
        ('<p class="animate-pulse">a<br>b</p>', ["ab"]),
        ('<div class="animate-pulse"><span>live</span></div>', ["live"]),
        ('<span class="w-2 animate-pulse"></span>LIVE', []),
        ('<span class="animate-pulsed">LIVE</span>', []),
    ],
    ids=["glyph-and-word", "variant", "void-child", "nested", "mark", "lookalike"],
)
def test_the_check_finds_text_in_a_pulse(markup: str, expected: list[str]) -> None:
    """The parser reports pulsing words, under variants and through nesting."""
    parser = _PulsingText()
    parser.feed(markup)
    assert parser.found == expected
