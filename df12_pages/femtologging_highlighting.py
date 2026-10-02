"""The instrument palette for femtologging's generated code panels.

The style owns token colours; the CSS generator exposes them as semantic
variables in the sub-site stylesheet. All token colours are read on carbon.
"""

import typing as typ

from pygments.style import Style
from pygments.token import (
    Comment,
    Error,
    Generic,
    Keyword,
    Name,
    Number,
    Operator,
    Punctuation,
    String,
    Text,
)


class FemtoStyle(Style):
    """Teal instruments, amber literals, and alumina text on carbon."""

    background_color = "#12171b"
    highlight_color = "#1d252b"
    default_style = ""
    styles: typ.ClassVar = {  # ty: ignore[invalid-attribute-override]  # Pygments declares its class map without ClassVar.
        Text: "#f2eee6",
        Comment: "#aeb8bf",
        Error: "#e8a293",
        Generic: "#f2eee6",
        Keyword: "#63d6cf",
        Name: "#f2eee6",
        Name.Builtin: "#8fe9f3",
        Name.Function: "#8fe9f3",
        Name.Class: "#8fe9f3",
        String: "#e1a64b",
        Number: "#e1a64b",
        Operator: "#aeb8bf",
        Punctuation: "#aeb8bf",
    }
