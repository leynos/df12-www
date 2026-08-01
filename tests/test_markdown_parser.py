"""Unit tests for the markdown section parser.

These tests cover the synthetic Introduction section built from the prose
that sits between a guide's top-level heading and its first ``##`` section,
which previous versions of the parser silently discarded.

Usage
-----
Run ``pytest tests/test_markdown_parser.py -v`` or ``make test``.
"""

from __future__ import annotations

from df12_pages.markdown_parser import parse_sections


def test_preamble_becomes_introduction_section() -> None:
    """Prose between the H1 and the first ## heading is kept as Introduction."""
    doc = (
        "# Guide Title\n\n"
        "This preamble explains the tool.\n\n"
        "Second preamble paragraph.\n\n"
        "## Installation\n\nBody.\n"
    )
    sections = parse_sections(doc)
    assert [s.title for s in sections] == ["Introduction", "Installation"]
    intro = sections[0]
    assert intro.slug == "introduction"
    assert intro.order == 1
    assert "This preamble explains the tool." in intro.markdown
    assert "Guide Title" not in intro.markdown
    expected_second_order = 2
    assert sections[1].order == expected_second_order


def test_title_only_preamble_adds_no_section() -> None:
    """A document whose H1 is immediately followed by ## gains no extra section."""
    doc = "# Guide Title\n\n## Installation\n\nBody.\n"
    sections = parse_sections(doc)
    assert [s.title for s in sections] == ["Installation"]
    assert sections[0].order == 1


def test_preamble_coexists_with_explicit_introduction() -> None:
    """A synthetic Introduction must not steal an existing section's slug."""
    doc = (
        "# Guide Title\n\nPreamble prose.\n\n## Introduction\n\nExplicit intro body.\n"
    )
    sections = parse_sections(doc)
    assert [s.slug for s in sections] == ["introduction", "introduction-2"]
