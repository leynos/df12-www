"""Tests for the generated Episodic syntax-highlighting stylesheet."""

from __future__ import annotations

import re

from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers import get_lexer_by_name

from df12_pages.episodic_highlighting import EpisodicStyle
from scripts.generate_episodic_pygments_css import STYLESHEET, build_css

LEXER_SAMPLES = {
    "bash": '# publish\necho "episode"\n',
    "console": '$ curl /episodes\n{"status": "ok"}\n',
    "json": '{"episode": 42, "ready": true}\n',
    "make": "build:\n\tbun run build\n",
    "xml": '<episode id="42"><title>Signal</title></episode>\n',
}


def test_committed_stylesheet_matches_the_generator() -> None:
    """The checked-in stylesheet is regenerated from the Pygments style."""
    assert STYLESHEET.read_text(encoding="utf-8") == build_css(), (
        f"{STYLESHEET} is stale; rerun scripts/generate_episodic_pygments_css.py"
    )


def test_every_token_family_has_an_explicit_colour() -> None:
    """Every Episodic token family resolves to the deliberate signal palette."""
    missing = [
        token
        for token in EpisodicStyle.styles
        if not EpisodicStyle.style_for_token(token)["color"]
    ]
    assert not missing, f"token families without an explicit colour: {missing}"


def test_generator_targets_tracked_static_source() -> None:
    """Generated syntax CSS must be copied from source, never written to public."""
    assert STYLESHEET.parts[-6:] == (
        "src",
        "static",
        "episodic",
        "assets",
        "styles",
        "syntax.css",
    )


def test_generated_css_styles_every_class_the_configured_lexers_emit() -> None:
    """Configured Episodic lexers never emit an uncoloured token span.

    Pygments renders subtype classes such as ``c1`` and ``s2`` while the
    style can declare an ancestor token. Each emitted class chain therefore
    needs at least one selector in the generated stylesheet, rather than a
    literal selector for every subtype name.
    """
    css = build_css()
    styled_classes = {
        name
        for chain in re.findall(r"\.episodic-syntax \.([\w.-]+)", css)
        for name in chain.split(".")
    }

    for lexer_name, source in LEXER_SAMPLES.items():
        markup = highlight(
            source,
            get_lexer_by_name(lexer_name),
            HtmlFormatter(cssclass="episodic-syntax", wrapcode=True),
        )
        class_attributes = [
            value
            for value in re.findall(r'class="([^"]*)"', markup)
            if value != "episodic-syntax"
        ]
        unstyled = [
            value
            for value in class_attributes
            if not set(value.split()).intersection(styled_classes)
        ]

        assert class_attributes, f"{lexer_name} should emit token classes"
        assert not unstyled, f"{lexer_name} emits unstyled classes: {unstyled}"
