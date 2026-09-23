"""Tests for the Cuprum Pygments style and its generated stylesheet block."""

from __future__ import annotations

import re

from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers import get_lexer_by_name

from df12_pages.cuprum_highlighting import CuprumStyle
from scripts.generate_cuprum_pygments_css import (
    BEGIN,
    CSS_CLASS,
    END,
    STYLESHEET,
    build_css,
)

#: The code ground the sub-site sets every highlighted block on.
CODE_GROUND = "#101817"
#: WCAG 2.2 AA floor for body text.
MIN_CONTRAST = 4.5
#: sRGB threshold below which the transfer function is linear.
_SRGB_LINEAR_CUTOFF = 0.04045

#: One sample per lexer the templates use, covering the token families the
#: pages actually show: imports, definitions, docstrings, f-strings, numbers,
#: comments, and a console transcript.
LEXER_SAMPLES = {
    "python": (
        "import asyncio\n"
        "\n"
        "from cuprum import ECHO, RunOutputOptions, sh\n"
        "\n"
        "\n"
        "async def main() -> None:\n"
        '    """Run one approved command."""\n'
        "    # Pick a known fitting from the catalogue.\n"
        '    cmd = sh.make(ECHO)("-n", "hello")\n'
        "    result = await cmd.run(output=RunOutputOptions(echo=True))\n"
        '    print(f"exit {result.exit_code}", 0x10, 3.5)\n'
    ),
    "console": "$ CUPRUM_STREAM_BACKEND=python python my_script.py\nFalse\n",
}


def _relative_luminance(colour: str) -> float:
    """Return the WCAG relative luminance of a ``#rrggbb`` colour."""

    def channel(value: int) -> float:
        """Return one 0-255 channel linearized per the sRGB transfer function."""
        fraction = value / 255
        if fraction <= _SRGB_LINEAR_CUTOFF:
            return fraction / 12.92
        return ((fraction + 0.055) / 1.055) ** 2.4

    digits = colour.lstrip("#")
    red, green, blue = (int(digits[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def _contrast_ratio(foreground: str, background: str) -> float:
    """Return the WCAG contrast ratio between two ``#rrggbb`` colours."""
    first, second = _relative_luminance(foreground), _relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def test_style_background_is_the_code_ground() -> None:
    """The style is authored against the ground the stylesheet paints."""
    assert CuprumStyle.background_color == CODE_GROUND


def test_every_token_colour_clears_the_body_text_floor() -> None:
    """Each declared colour meets WCAG 2.2 AA against the code ground."""
    failures = []
    for token, spec in CuprumStyle.styles.items():
        colour = next((word for word in spec.split() if word.startswith("#")), "")
        if colour and _contrast_ratio(colour, CODE_GROUND) < MIN_CONTRAST:
            failures.append(f"{token} {colour}")
    assert not failures, f"token colours below {MIN_CONTRAST}:1: {failures}"


def test_generated_css_styles_every_class_the_samples_emit() -> None:
    """Every span Pygments emits for the pages' lexers carries a styled class.

    Pygments emits the most specific class it has for a token while the style
    declares broad categories, so a generator that wrote one rule per declared
    token would leave most spans unstyled. See scripts/pygments_css.py.
    """
    styled = {
        name
        for chain in re.findall(rf"\.{CSS_CLASS} \.([\w.-]+)", build_css())
        for name in chain.split(".")
    }
    for lexer, source in LEXER_SAMPLES.items():
        markup = highlight(
            source,
            get_lexer_by_name(lexer),
            HtmlFormatter(cssclass=CSS_CLASS, wrapcode=True),
        )
        attributes = [
            value
            for value in re.findall(r'class="([^"]*)"', markup)
            if value != CSS_CLASS
        ]
        unstyled = [value for value in attributes if not set(value.split()) & styled]
        assert attributes, f"the {lexer} sample should produce token classes"
        assert not unstyled, f"{lexer}: spans with no styled class: {sorted(unstyled)}"


def test_committed_stylesheet_matches_the_generator() -> None:
    """The checked-in block is regenerated, never hand-edited."""
    css = STYLESHEET.read_text(encoding="utf-8")
    start, end = css.find(BEGIN), css.find(END)

    assert start != -1, f"{STYLESHEET} should carry the BEGIN marker"
    assert end != -1, f"{STYLESHEET} should carry the END marker"
    assert css[start : end + len(END)] == build_css(), (
        f"{STYLESHEET} is stale; rerun scripts/generate_cuprum_pygments_css.py"
    )


def test_layout_rules_stay_above_the_generated_block() -> None:
    """The generator owns tokens; handwritten CSS owns layout."""
    css = STYLESHEET.read_text(encoding="utf-8")
    marker = css.index(BEGIN)
    # The generator also emits a bare `.cuprum-syntax { color: ... }` rule, so
    # the layout rule is identified by its first declaration.
    layout_rules = (
        ".code-scroll {",
        f".{CSS_CLASS} {{\n  width: max-content;",
        f".{CSS_CLASS} pre {{",
    )
    for rule in layout_rules:
        assert rule in css[:marker], f"{rule!r} should stay above the marker"
        assert rule not in build_css(), f"{rule!r} should not be generated"


def test_generator_writes_to_the_tracked_stylesheet() -> None:
    """The target is the tracked source, not the git-ignored build output."""
    assert STYLESHEET.parts[-6:] == (
        "src",
        "static",
        "cuprum",
        "assets",
        "styles",
        "syntax.css",
    ), f"unexpected stylesheet target: {STYLESHEET}"
