"""Unit tests for build-time Mermaid rendering in the HTML content renderer.

These tests stub the Mermaid CLI layer so no external process runs. They
cover the fence-to-figure replacement, the fallback to highlighted code when
rendering fails, the per-diagram SVG id uniquification, and the split between
preparing a document's diagrams and rendering it once they are prepared.

Usage
-----
Run ``pytest tests/test_mermaid_render.py -v`` or ``make test``.
"""

from __future__ import annotations

import typing as typ

from df12_pages.generator.renderer import HtmlContentRenderer, MermaidRenderer

if typ.TYPE_CHECKING:
    import pytest


class _CountingMermaid(MermaidRenderer):
    """A Mermaid renderer whose output is a stub and whose calls are counted."""

    def __init__(self, svg: str | None = "<svg>diagram</svg>") -> None:
        """Store the SVG to answer with, or ``None`` to fail every diagram."""
        super().__init__(executable="unused")
        self._svg = svg
        self.sources: list[str] = []

    def render(self, source: str) -> str | None:
        """Record the diagram source and return the stub SVG."""
        self.sources.append(source)
        return self._svg


SAMPLE_MARKDOWN = """Intro paragraph.

```mermaid
flowchart LR
  A --> B
```

Closing paragraph.
"""


def test_mermaid_fence_rendered_to_figure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A mermaid fence becomes an inline SVG figure, not a code block."""
    monkeypatch.setattr(
        MermaidRenderer, "render", lambda self, source: "<svg>diagram</svg>"
    )
    html = HtmlContentRenderer().markdown(SAMPLE_MARKDOWN)
    assert '<figure class="doc-mermaid"><svg>diagram</svg></figure>' in html
    assert "codehilite" not in html, "rendered diagrams must not fall through"
    assert "df12-mermaid-placeholder" not in html, "placeholder tokens must resolve"


def test_mermaid_fence_falls_back_to_code_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fence whose diagram fails to render stays a highlighted code block."""
    monkeypatch.setattr(MermaidRenderer, "render", lambda self, source: None)
    html = HtmlContentRenderer().markdown(SAMPLE_MARKDOWN)
    assert "<figure" not in html
    assert 'data-language="mermaid"' in html


def test_multiple_diagrams_each_rendered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every mermaid fence in a document is replaced independently."""
    calls: list[str] = []

    def _fake_render(self: MermaidRenderer, source: str) -> str:
        """Record the diagram source and return a numbered stub SVG."""
        calls.append(source)
        return f"<svg>d{len(calls)}</svg>"

    monkeypatch.setattr(MermaidRenderer, "render", _fake_render)
    doc = SAMPLE_MARKDOWN + "\n```mermaid\nsequenceDiagram\n  A->>B: hi\n```\n"
    html = HtmlContentRenderer().markdown(doc)
    expected_diagrams = 2
    assert len(calls) == expected_diagrams
    assert "<svg>d1</svg>" in html
    assert "<svg>d2</svg>" in html


def test_svg_ids_uniquified_per_diagram(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI's fixed ``merman`` id is rewritten per diagram source."""
    monkeypatch.setattr(
        MermaidRenderer,
        "_invoke",
        lambda self, source: '<svg id="merman"><style>#merman a{}</style></svg>',
    )
    renderer = MermaidRenderer()
    first = renderer.render("flowchart LR\n A-->B")
    second = renderer.render("flowchart LR\n C-->D")
    assert first is not None
    assert second is not None
    assert 'id="merman"' not in first
    assert "#merman a" not in first
    first_id = first.split('id="')[1].split('"')[0]
    second_id = second.split('id="')[1].split('"')[0]
    assert first_id != second_id, "distinct sources must get distinct SVG ids"


def test_render_failures_cached_and_reported(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing CLI yields None once per distinct source and warns on stderr."""
    renderer = MermaidRenderer(executable="/nonexistent/merman-cli")
    assert renderer.render("flowchart LR\n A-->B") is None
    assert renderer.render("flowchart LR\n A-->B") is None
    err = capsys.readouterr().err
    assert err.count("mermaid rendering failed") == 1, "second call must hit the cache"


def test_preparing_a_document_compiles_each_diagram_exactly_once() -> None:
    """Preparation owns the subprocess; rendering the result starts none."""
    mermaid = _CountingMermaid()
    renderer = HtmlContentRenderer(mermaid=mermaid)

    prepared = renderer.prepare_markdown(SAMPLE_MARKDOWN)
    first = renderer.render_prepared(prepared)
    second = renderer.render_prepared(prepared)

    assert len(mermaid.sources) == 1, (
        f"preparation must compile the diagram once, got {mermaid.sources!r}"
    )
    assert first == second, "a prepared document must render deterministically"
    assert '<figure class="doc-mermaid"><svg>diagram</svg></figure>' in first, (
        "a compiled diagram must be restored as a figure"
    )
    assert "df12-mermaid-placeholder" not in first, (
        "every placeholder token must be replaced by its figure"
    )


def test_preparation_keeps_an_uncompilable_fence_for_the_fallback() -> None:
    """A diagram that failed to compile is left as a fence in the prepared text."""
    renderer = HtmlContentRenderer(mermaid=_CountingMermaid(svg=None))

    prepared = renderer.prepare_markdown(SAMPLE_MARKDOWN)
    html = renderer.render_prepared(prepared)

    assert "```mermaid" in prepared.markdown, (
        "the fence must survive preparation so rendering can highlight it"
    )
    assert not prepared.figures, "a failed diagram contributes no figure"
    assert 'data-language="mermaid"' in html, (
        "a failed diagram must fall back to a highlighted code block"
    )


def test_the_cli_override_is_read_when_invoked_not_when_constructed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Constructing a renderer must not capture ambient configuration."""
    monkeypatch.setenv("DF12_MERMAID_CLI", "/first/mermaid")
    renderer = MermaidRenderer()
    monkeypatch.setenv("DF12_MERMAID_CLI", "/second/mermaid")

    assert renderer.executable == "/second/mermaid", (
        "the override belongs to the invocation, not to construction"
    )
