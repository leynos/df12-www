"""The beam palette for wireframe's generated code panels.

The style owns token colours; the CSS generator exposes them as variables in
the sub-site stylesheet. Every colour is read on the panel ground, ``#091A16``,
where the faintest token, the muted comment, holds 9.26:1.
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


class ScopeStyle(Style):
    """Mint keywords, cyan names, amber literals, and ink text on the panel.

    The beam roles follow the colour and beam system: mint signals structure,
    cyan marks the things that travel, amber marks values on the active path,
    and magenta, the rare colour, is kept for attributes and macros.
    """

    background_color = "#091a16"
    highlight_color = "#102720"
    default_style = ""
    styles: typ.ClassVar = {  # ty: ignore[invalid-attribute-override]  # Pygments declares its class map without ClassVar.
        Text: "#f1fff8",
        Comment: "#9fc2b3",
        Comment.Preproc: "#ff6ad5",
        Error: "#ff6ad5",
        Generic: "#f1fff8",
        Keyword: "#7cffb3",
        Name: "#f1fff8",
        Name.Attribute: "#ff6ad5",
        Name.Builtin: "#00ffff",
        Name.Class: "#00ffff",
        Name.Function: "#00ffff",
        Name.Function.Magic: "#ff6ad5",
        Name.Namespace: "#9fc2b3",
        String: "#ffb347",
        String.Doc: "#9fc2b3",
        Number: "#ffb347",
        Operator: "#9fc2b3",
        Punctuation: "#9fc2b3",
    }
