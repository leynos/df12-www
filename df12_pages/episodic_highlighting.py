"""The Episodic Pygments highlighting style.

Code sits on ``--surface-inset`` (``#08090a``), the darkest ground on the
subsite, so every colour below is drawn from the Episodic signal palette and
checked at a minimum 4.5:1 against that ground. The lowest is the comment
grey at 6.6:1, which leaves room for the palette to shift without a token
quietly dropping below the floor.

Signals keep their meaning here: cyan is information, so it carries keywords;
amber is attention, so it carries literals; green is success, so it marks the
shell prompt and built-ins; red is failure, so it is reserved for errors.
Violet is the one hue with no status role, which is why it can name functions
and classes without implying anything about them.

The values are mirrored by the generated ``.episodic-syntax`` rules in
``src/static/episodic/assets/styles/syntax.css``. Regenerate those with
``uv run python scripts/generate_episodic_pygments_css.py`` after changing
this module.

Unlike the Netsuke and Stilyagi styles, this one is not registered through a
Pygments entry point. Nothing needs to resolve it by name: the highlight tag
emits token classes only, and the colours arrive from the generated
stylesheet, so the style exists purely to author that stylesheet.
"""

from __future__ import annotations

import typing as typ

from pygments.style import Style
from pygments.token import (
    Comment,
    Error,
    Generic,
    Keyword,
    Literal,
    Name,
    Number,
    Operator,
    Punctuation,
    Token,
)


class EpisodicStyle(Style):
    """Pygments style drawn from the Episodic signal palette."""

    name = "episodic"
    background_color = "#08090a"
    highlight_color = "#1e2226"

    # Pygments token types are not publicly typed, so the key is Any.
    styles: typ.ClassVar[dict[typ.Any, str]] = {
        Token: "#e6e7e9",  # ink-1: default code text
        Comment: "italic #8f959c",  # 6.6:1, the lowest ratio in the style
        Comment.Preproc: "#3bc8ef",
        Keyword: "#3bc8ef",  # cyan: information
        Operator: "#b8bbc0",  # ink-2: structure, quieter than the terms
        Punctuation: "#b8bbc0",
        Name: "#e6e7e9",
        Name.Class: "#b77aff",  # violet: the hue with no status role
        Name.Function: "#b77aff",
        Name.Decorator: "#b77aff",
        Name.Tag: "#3bc8ef",  # XML and TEI element names
        Name.Attribute: "#3ad07a",
        Name.Builtin: "#3ad07a",  # green
        Name.Builtin.Pseudo: "#3ad07a",
        Literal: "#ffb520",
        Literal.String: "#ffb520",  # amber: attention
        Literal.String.Doc: "italic #8f959c",  # docstrings read as commentary
        Literal.String.Escape: "#ff5148",
        Number: "#ffb520",
        Generic.Prompt: "bold #3ad07a",  # the $ in a shell session
        Generic.Output: "#b8bbc0",  # program output, quieter than commands
        Generic.Error: "#ff5148",
        Generic.Traceback: "#ff5148",
        Error: "#ff5148",  # red: failure
    }


__all__ = ["EpisodicStyle"]
