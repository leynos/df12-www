"""The Stilyagi Pygments highlighting style.

The Stilyagi sub-site sets code on the lamp-black ``--ink`` ground, so the
paper-surface palette is unusable here: the press red, the sage, and the
magenta all fall below the 4.5:1 body-text floor against it. Every colour
below is therefore a tint of a Stilyagi hue chosen to clear that floor
against ``#0f0f0f``, mirroring how ``HimotoshiStyle`` is tuned against the
Netsuke charcoal.

The style's values are mirrored by the generated ``.stilyagi-syntax`` rules
in ``src/static/stilyagi/assets/styles/syntax.css``; regenerate those with
``scripts/generate_stilyagi_pygments_css.py`` after changing this module.

The style is registered with Pygments through the ``pygments.styles`` entry
point declared in ``pyproject.toml``, so ``get_style_by_name("stilyagi")``
resolves anywhere in the pipeline.
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


class StilyagiStyle(Style):
    """Pygments style drawn from the Stilyagi palette.

    Every colour is checked at a minimum 4.5:1 contrast ratio against the
    ``--ink`` background used by the sub-site's code windows.
    """

    name = "stilyagi"
    background_color = "#0f0f0f"
    highlight_color = "#2a2a2a"

    styles: typ.ClassVar[dict[typ.Any, str]] = {
        Token: "#efe4ce",  # paper: default text
        Comment: "italic #827b6a",  # lightened rule-faint; 4.6:1
        Comment.Preproc: "#d69f2e",  # jazz ochre
        Keyword: "#29b4c4",  # jazz cyan
        Operator: "#efe4ce",  # paper
        Punctuation: "#efe4ce",
        Name: "#efe4ce",
        Name.Class: "#e22d85",  # lightened jazz magenta; 4.5:1
        Name.Function: "#e22d85",
        Name.Decorator: "#d69f2e",
        Name.Builtin: "#787f4e",  # lightened signal sage; 4.5:1
        Name.Builtin.Pseudo: "#787f4e",
        Literal.String: "#d69f2e",  # jazz ochre
        Literal.String.Doc: "italic #827b6a",  # docstrings read as commentary
        Literal.String.Escape: "#da474e",  # press red on the ink ground
        Number: "#d69f2e",
        Generic.Prompt: "bold #787f4e",
        Generic.Output: "#efe4ce",
        Generic.Error: "#da474e",
        Error: "#da474e",
    }


__all__ = ["StilyagiStyle"]
