"""Direct tests for turning a parsed section into template blocks.

The helpers in :mod:`df12_pages.generator.section_render` are exercised here
with hand-built sections, so each rule they implement -- step ordering, anchor
ownership, block selection and figure pass-through -- is asserted on the value
they return rather than through a rendered page.

Usage
-----
Run ``pytest tests/test_section_render.py -v`` or ``make test``.
"""

from __future__ import annotations

import typing as typ

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from df12_pages.config import SectionLayout
from df12_pages.generator.renderer import HtmlContentRenderer, MermaidRenderer
from df12_pages.generator.section_render import (
    prepare_numbered_steps,
    prepare_split_panel,
)
from df12_pages.markdown_parser import Section, Subsection

if typ.TYPE_CHECKING:
    import collections.abc as cabc


class _StubRenderer(HtmlContentRenderer):
    """A renderer whose output names the markdown it was handed."""

    def __init__(self) -> None:
        """Bind a renderer that records the ref each conversion was given."""
        super().__init__()
        self.seen_refs: list[str | None] = []

    def markdown(
        self,
        text: str,
        *,
        figures: cabc.Mapping[str, str] | None = None,
        link_ref: str | None = None,
    ) -> str:
        """Wrap the markdown in a paragraph, as a conversion would."""
        self.seen_refs.append(link_ref)
        if figures is not None:
            for token, figure in figures.items():
                text = text.replace(token, figure)
        return f"<p>{text}</p>" if text else ""

    def code_block(self, code: str, language: str | None = None) -> str:
        """Return the snippet with its language, as highlighting would."""
        lang = language or "text"
        return f'<pre data-language="{lang}">{code}</pre>'


class _StubMermaid(MermaidRenderer):
    """A Mermaid renderer whose diagrams compile to a fixed, visible SVG."""

    def __init__(self) -> None:
        """Bind a renderer that never invokes the CLI."""
        super().__init__(executable="unused")

    def render(self, source: str) -> str | None:
        """Return the same compiled SVG for every diagram source."""
        return "<svg>compiled</svg>"


def _section(
    *,
    markdown: str = "",
    subsections: list[Subsection] | None = None,
) -> Section:
    """Build a one-section document with the supplied body and subsections."""
    return Section(
        title="Guide",
        short_title="Guide",
        slug="guide",
        order=1,
        markdown=markdown,
        intro_markdown="",
        subsections=list(subsections or []),
    )


def test_step_order_reorders_subsections_case_insensitively() -> None:
    """A step order names subsections regardless of case and leads the list."""
    subsections = [
        Subsection("Alpha", "alpha body"),
        Subsection("Beta", "beta body"),
        Subsection("Gamma", "gamma body"),
    ]
    layout = SectionLayout(device="numbered_steps", step_order=["gamma", "ALPHA"])

    steps = prepare_numbered_steps(
        _StubRenderer(), _section(subsections=subsections), layout, figures={}
    )

    assert [step["title"] for step in steps] == ["Gamma", "Alpha", "Beta"], (
        "listed steps lead in the listed order; unlisted ones keep their own "
        f"order, got {[step['title'] for step in steps]!r}"
    )
    assert [step["number"] for step in steps] == [1, 2, 3], (
        "steps are renumbered in the order they are shown"
    )


def test_a_repeated_step_order_entry_does_not_repeat_a_step() -> None:
    """Naming one subsection twice orders it once."""
    subsections = [Subsection("Alpha", "a"), Subsection("Beta", "b")]
    layout = SectionLayout(step_order=["Beta", "beta", "Alpha"])

    steps = prepare_numbered_steps(
        _StubRenderer(), _section(subsections=subsections), layout, figures={}
    )

    assert [step["title"] for step in steps] == ["Beta", "Alpha"], (
        f"each subsection must appear once, got {[step['title'] for step in steps]!r}"
    )


def test_a_reordering_carries_each_anchor_with_its_subsection() -> None:
    """Anchors are positional, so a step keeps the anchor its content earned."""
    subsections = [
        Subsection("Alpha", "a"),
        Subsection("Beta", "b"),
        Subsection("Gamma", "c"),
    ]
    layout = SectionLayout(step_order=["Gamma", "Alpha", "Beta"])

    steps = prepare_numbered_steps(
        _StubRenderer(),
        _section(subsections=subsections),
        layout,
        figures={},
        subsection_anchors=["guide-alpha", "guide-beta", "guide-gamma"],
    )

    assert [step["content_anchor"] for step in steps] == [
        "guide-gamma",
        "guide-alpha",
        "guide-beta",
    ], "each anchor must travel with the subsection it was built for"
    assert [step["anchor"] for step in steps] == [
        "guide-step-1",
        "guide-step-2",
        "guide-step-3",
    ], "the positional step anchors follow the displayed order"


def test_two_subsections_that_share_a_title_keep_distinct_anchors() -> None:
    """Duplicate titles do not collapse onto one content anchor."""
    subsections = [
        Subsection("Install", "first install"),
        Subsection("Install", "second install"),
    ]

    steps = prepare_numbered_steps(
        _StubRenderer(),
        _section(subsections=subsections),
        SectionLayout(device="numbered_steps"),
        figures={},
        subsection_anchors=["guide-install", "guide-install-2"],
    )

    assert [step["content_anchor"] for step in steps] == [
        "guide-install",
        "guide-install-2",
    ], "each occurrence must keep the anchor its own content earned"


def test_a_subsection_without_an_anchor_keeps_its_step_anchor() -> None:
    """A missing anchor entry falls back to the positional step anchor."""
    subsections = [Subsection("Alpha", "a"), Subsection("Beta", "b")]

    steps = prepare_numbered_steps(
        _StubRenderer(),
        _section(subsections=subsections),
        SectionLayout(device="numbered_steps"),
        figures={},
        subsection_anchors=["guide-alpha"],
    )

    assert steps[0]["content_anchor"] == "guide-alpha"
    assert steps[1]["content_anchor"] == "guide-step-2", (
        "the unanchored step must not borrow its neighbour's anchor"
    )


_TITLE_POOL = st.integers(min_value=0, max_value=12)


def _pool_title(index: int, *, upper: bool = False) -> str:
    """Return a title from the shared pool, optionally uppercased."""
    return f"STEP{index}" if upper else f"Step{index}"


@given(
    title_ids=st.lists(_TITLE_POOL, unique=True, max_size=6),
    order_ids=st.lists(_TITLE_POOL, max_size=6),
    anchor_count=st.integers(min_value=0, max_value=6),
)
@settings(max_examples=100)
def test_numbered_steps_preserve_each_subsection_and_its_anchor(
    title_ids: list[int], order_ids: list[int], anchor_count: int
) -> None:
    """Every subsection appears once, in the ordered prefix, with its anchor."""
    titles = [_pool_title(index) for index in title_ids]
    order = [_pool_title(index, upper=index % 2 == 0) for index in order_ids]
    subsections = [
        Subsection(title, f"body-{position}") for position, title in enumerate(titles)
    ]
    anchors = [f"guide-anchor-{position}" for position in range(anchor_count)]
    body_to_position = {
        f"<p>body-{position}</p>": position for position in range(len(subsections))
    }

    steps = prepare_numbered_steps(
        _StubRenderer(),
        _section(subsections=subsections),
        SectionLayout(device="numbered_steps", step_order=order),
        figures={},
        subsection_anchors=anchors,
    )

    positions = [body_to_position[step["html"]] for step in steps]
    assert sorted(positions) == list(range(len(subsections))), (
        f"each subsection must appear exactly once, got {positions!r}"
    )
    assert [step["number"] for step in steps] == list(range(1, len(steps) + 1)), (
        "numbering must follow the displayed order"
    )

    by_lower = {title.lower(): title for title in titles}
    matched: list[str] = []
    seen: set[str] = set()
    for desired in order:
        key = desired.lower()
        if key in by_lower and key not in seen:
            matched.append(by_lower[key])
            seen.add(key)
    remaining = [title for title in titles if title.lower() not in seen]
    assert [step["title"] for step in steps] == matched + remaining, (
        "named subsections must lead in the named order, and the rest must "
        "keep their original order"
    )

    for step, position in zip(steps, positions, strict=True):
        assert step["anchor"] == f"guide-step-{step['number']}", (
            "the positional anchor must follow the displayed order"
        )
        if position < len(anchors):
            assert step["content_anchor"] == anchors[position], (
                "a content anchor must travel with its own subsection"
            )
        else:
            assert step["content_anchor"] == f"guide-step-{step['number']}", (
                "a subsection with no anchor falls back to its step anchor"
            )


def test_no_subsections_yields_no_numbered_steps() -> None:
    """A section without subsections has nothing to number."""
    steps = prepare_numbered_steps(
        _StubRenderer(),
        _section(),
        SectionLayout(device="numbered_steps", step_order=["Alpha"]),
        figures={},
    )

    assert steps == []


def test_a_numbered_step_carries_its_compiled_figure() -> None:
    """The figures mapping reaches the step's HTML."""
    renderer = HtmlContentRenderer(mermaid=_StubMermaid())
    prepared = renderer.prepare_markdown("```mermaid\ngraph TD; A-->B\n```\n")
    section = _section(subsections=[Subsection("Only step", prepared.markdown)])

    steps = prepare_numbered_steps(
        renderer,
        section,
        SectionLayout(device="numbered_steps"),
        figures=prepared.figures,
    )

    assert "<svg>compiled</svg>" in steps[0]["html"], (
        "a dropped figures mapping would leave the placeholder in place: "
        f"{steps[0]['html']!r}"
    )
    assert "df12-mermaid-placeholder" not in steps[0]["html"]


def test_a_section_without_a_code_block_stays_in_the_primary_panel() -> None:
    """Nothing moves to the secondary panel when there is no block to move."""
    panel = prepare_split_panel(
        _StubRenderer(),
        _section(markdown="Prose only."),
        SectionLayout(device="split_panel"),
        {},
    )

    assert panel == {
        "primary_html": "<p>Prose only.</p>",
        "secondary_html": "",
    }, "the whole section must render in the primary panel"


def test_the_emphasized_block_moves_to_the_secondary_panel() -> None:
    """The named block is highlighted separately and leaves the primary HTML."""
    markdown = (
        "Before.\n\n```rust\nlet x = 1;\n```\n\n"
        "Between.\n\n```python\ny = 2\n```\n\nAfter."
    )

    panel = prepare_split_panel(
        _StubRenderer(),
        _section(markdown=markdown),
        SectionLayout(device="split_panel", emphasized_code_block=1),
        {},
    )

    assert "y = 2" in panel["secondary_html"], (
        f"the selected block must be highlighted, got {panel!r}"
    )
    assert "y = 2" not in panel["primary_html"], (
        "the selected block must not also appear in the primary panel"
    )
    assert "let x = 1" in panel["primary_html"], (
        "the unselected block stays in the primary markdown"
    )
    assert "Between." in panel["primary_html"], (
        "the prose around a removed block must survive"
    )


@pytest.mark.parametrize("index", [-1, 2])
def test_an_out_of_range_index_falls_back_to_the_first_block(index: int) -> None:
    """An index past the blocks, including a negative one, selects the first."""
    markdown = "```rust\nfirst block\n```\n\n```python\nsecond block\n```"

    panel = prepare_split_panel(
        _StubRenderer(),
        _section(markdown=markdown),
        SectionLayout(device="split_panel", emphasized_code_block=index),
        {},
    )

    assert "first block" in panel["secondary_html"], (
        f"index {index} must fall back to the first block, got {panel!r}"
    )
    assert "second block" in panel["primary_html"], (
        "an out-of-range index must not move the last block"
    )


def test_the_primary_panel_carries_the_section_s_compiled_figure() -> None:
    """The figures mapping reaches the primary HTML of a split panel."""
    renderer = HtmlContentRenderer(mermaid=_StubMermaid())
    prepared = renderer.prepare_markdown(
        "Intro.\n\n```mermaid\ngraph TD; A-->B\n```\n\n```rust\nlet x = 1;\n```\n"
    )

    panel = prepare_split_panel(
        renderer,
        _section(markdown=prepared.markdown),
        SectionLayout(device="split_panel"),
        prepared.figures,
    )

    assert "<svg>compiled</svg>" in panel["primary_html"], (
        "a dropped figures mapping would leave the placeholder in place: "
        f"{panel['primary_html']!r}"
    )
    assert 'data-language="rust"' in panel["secondary_html"], (
        "the code block still moves out of the primary panel"
    )


def test_numbered_steps_forward_the_document_ref_to_every_conversion() -> None:
    """Each step's markdown converts against the ref the document captured."""
    subsections = [Subsection("Alpha", "a"), Subsection("Beta", "b")]
    renderer = _StubRenderer()

    prepare_numbered_steps(
        renderer,
        _section(subsections=subsections),
        SectionLayout(device="numbered_steps"),
        figures={},
        link_ref="v1.0.0",
    )

    assert renderer.seen_refs == ["v1.0.0", "v1.0.0"], (
        f"every step must convert against the document ref, got {renderer.seen_refs!r}"
    )


def test_split_panels_forward_the_document_ref_to_every_conversion() -> None:
    """Both panels convert against the ref the document captured."""
    renderer = _StubRenderer()
    markdown = "Prose.\n\n```rust\nlet x = 1;\n```"

    prepare_split_panel(
        renderer,
        _section(markdown=markdown),
        SectionLayout(device="split_panel"),
        {},
        link_ref="main",
    )

    assert renderer.seen_refs == ["main"], (
        f"the primary panel must convert against the document ref, "
        f"got {renderer.seen_refs!r}"
    )
