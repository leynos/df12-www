"""The Cuprum Pygments highlighting style.

Cuprum sets code in the dispatch office's night panel, ``--color-code-ground``
(``#101817``), a teal-black darker than the charcoal ink. Every colour below
is checked at a minimum 4.5:1 against that ground; the lowest is the comment
patina at 6.4:1.

The roles follow the site's palette rather than decorating it. Copper-orange
carries keywords, the fittings a reader recognizes first; work-order yellow
carries strings and numbers, the values a command is given; lifted patina
carries names the program defines and the shell prompt; the paper cream is
body text. Salmon is reserved for errors.

The values are mirrored by the generated ``.cuprum-syntax`` rules in
``src/static/cuprum/assets/styles/syntax.css``. Regenerate those with
``uv run python scripts/generate_cuprum_pygments_css.py`` after changing this
module.

Like the Episodic style, this one is not registered through a Pygments entry
point: the highlight tag emits token classes only, and the colours arrive from
the generated stylesheet, so the style exists to author that stylesheet.
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


class CuprumStyle(Style):
    """Render Pygments tokens in the Cuprum dispatch-office palette.

    Every declared colour clears 4.5:1 against ``background_color``. Edit this
    class and rerun the generator rather than hand-editing the CSS it emits.
    """

    name = "cuprum"
    background_color = "#101817"
    highlight_color = "#1d2b29"

    # Pygments token types are not publicly typed, so the key is Any; the same
    # rationale applies in scripts/generate_cuprum_pygments_css.py.
    # The base class declares this attribute without `ClassVar`, which ty
    # reads as an instance variable; RUF012 still wants the annotation here.
    styles: typ.ClassVar[dict[typ.Any, str]] = {  # ty: ignore[invalid-attribute-override]
        Token: "#f8eedb",  # cream: default text, 15.7:1
        Comment: "italic #7fa19b",  # patina comment, 6.4:1
        Comment.Preproc: "#f28b55",
        Keyword: "#f28b55",  # copper-orange, 7.4:1
        Operator: "#c9c1ae",  # quieter than the terms it joins, 10.1:1
        Punctuation: "#c9c1ae",
        Name: "#f8eedb",
        Name.Class: "#9ed7c7",  # lifted patina, 11.2:1
        Name.Function: "#9ed7c7",
        Name.Decorator: "#9ed7c7",
        Name.Builtin: "#77c7bc",  # patina, 9.2:1
        Name.Builtin.Pseudo: "#77c7bc",
        Literal.String: "#e8c869",  # work-order yellow, 11.1:1
        Literal.String.Doc: "italic #7fa19b",  # docstrings read as commentary
        Literal.String.Escape: "#f5976f",
        Number: "#efb642",  # 9.8:1
        Generic.Prompt: "bold #77c7bc",
        Generic.Output: "#c9c1ae",
        Generic.Error: "#ff8a7a",  # 7.9:1
        Generic.Traceback: "#ff8a7a",
        Error: "#ff8a7a",
    }


__all__ = ["CuprumStyle"]
