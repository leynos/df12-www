"""Unit tests for build-time Mermaid rendering in the HTML content renderer.

These tests stub the Mermaid CLI layer so no external process runs. They
cover the fence-to-figure replacement, the fallback to highlighted code when
rendering fails, and the per-diagram SVG id uniquification.

Usage
-----
Run ``pytest tests/test_mermaid_render.py -v`` or ``make test``.
"""

from __future__ import annotations

import typing as typ

from df12_pages.generator.renderer import HtmlContentRenderer, MermaidRenderer

if typ.TYPE_CHECKING:
    import pytest

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
