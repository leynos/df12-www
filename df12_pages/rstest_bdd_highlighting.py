"""The rstest-bdd Pygments highlighting style.

rstest-bdd sets code on the picnic blanket at night, ``--color-night``
(``#16283a``), the night-blue felt of the site's dark bands. Every colour
below is checked at a minimum 4.5:1 against that ground; the lowest is the
attribute pumpkin at 6.8:1.

The roles follow the site's palette. Lantern yellow carries keywords, and
Gherkin's ``Given``, ``When``, and ``Then`` with them; pumpkin carries the
``#[given]`` and ``#[scenario]`` attributes and macro calls, the places
rstest-bdd touches the code; lifted moss carries strings, which is where a
step's pattern lives; lifted robot-teal carries types; starlight cream is body
text. Salmon is reserved for errors.

The values are mirrored by the generated ``.lantern-syntax`` rules in
``src/static/rstest-bdd/assets/styles/syntax.css``. Regenerate those with
``uv run python scripts/generate_rstest_bdd_pygments_css.py`` after changing
this module.

Like the Cuprum style, this one is not registered through a Pygments entry
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


class LanternStyle(Style):
    """Render Pygments tokens in the rstest-bdd lantern-picnic palette.

    Every declared colour clears 4.5:1 against ``background_color``. Edit this
    class and rerun the generator rather than hand-editing the CSS it emits.
    """

    name = "lantern"
    background_color = "#16283a"
    highlight_color = "#1f3850"

    # Pygments token types are not publicly typed, so the key is Any; the same
    # rationale applies in scripts/generate_rstest_bdd_pygments_css.py.
    # The base class declares this attribute without `ClassVar`, which ty
    # reads as an instance variable; RUF012 still wants the annotation here.
    styles: typ.ClassVar[dict[typ.Any, str]] = {  # ty: ignore[invalid-attribute-override]
        Token: "#f5e6c4",  # starlight: default text, 12.2:1
        Comment: "italic #a3b3b6",  # quiet thread, 6.9:1
        Comment.Preproc: "#f09a6a",  # pumpkin: attributes, 6.8:1
        Keyword: "#e9b44c",  # lantern yellow, 7.9:1
        Keyword.Type: "#a9d3cf",  # lifted robot-teal, 9.2:1
        Keyword.Constant: "#f0c567",
        Operator: "#c2c8c9",  # quieter than the terms it joins, 8.9:1
        Punctuation: "#c2c8c9",
        Name: "#f5e6c4",
        Name.Class: "#a9d3cf",
        Name.Builtin: "#a9d3cf",
        Name.Function: "#f7d9b0",  # warm cream, 11.1:1
        Name.Function.Magic: "#f09a6a",  # macro calls, as attributes
        Literal.String: "#c5d88f",  # lifted moss, 9.7:1
        Literal.String.Escape: "#f09a6a",
        Number: "#f0c567",  # 9.2:1
        Generic.Prompt: "bold #e9b44c",
        Generic.Output: "#c2c8c9",
        Generic.Error: "#ff9c8a",  # 7.4:1
        Generic.Traceback: "#ff9c8a",
        Error: "#ff9c8a",
    }


__all__ = ["LanternStyle"]
