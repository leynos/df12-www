"""Common Signal syntax colours on the dark code surface."""

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
    """Readable syntax roles for the Wireframe code panels."""

    background_color = "#0b1928"
    highlight_color = "#11283a"
    default_style = ""
    styles: typ.ClassVar = {  # ty: ignore[invalid-attribute-override]  # Pygments declares its class map without ClassVar.
        Text: "#edf6ff",
        Comment: "#bed0de",
        Comment.Preproc: "#63ebf4",
        Error: "#fe536c",
        Generic: "#edf6ff",
        Keyword: "#38f49d",
        Name: "#edf6ff",
        Name.Attribute: "#63ebf4",
        Name.Builtin: "#63ebf4",
        Name.Class: "#63ebf4",
        Name.Function: "#63ebf4",
        Name.Function.Magic: "#63ebf4",
        Name.Namespace: "#bed0de",
        String: "#edf6ff",
        String.Doc: "#bed0de",
        Number: "#edf6ff",
        Operator: "#bed0de",
        Punctuation: "#bed0de",
    }
