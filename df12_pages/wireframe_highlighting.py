"""The Common Signal palette for wireframe's generated code panels.

The style owns token colours; the CSS generator exposes them as variables in
the sub-site stylesheet. Every colour is read on the surface ground,
``#0B1928``, and on the raised line highlight, ``#11283A``; the faintest
token there, the lifted cobalt of keywords, holds 5.88:1.
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


class SignalStyle(Style):
    """Cobalt keywords, signal names, flow literals, and ink text on surface.

    The palette of responsibility, applied to code without inventing meaning:
    keywords and attributes carry the structural cobalt, in the lifted cut
    that passes as text; types and functions are the information in signal
    cyan; literals, the values that travel, are flow green; comments and
    punctuation recede to the muted ramp. Halt is kept for errors. Capacity
    and notice are not used, because no token means a budget or a notice.
    """

    background_color = "#0b1928"
    highlight_color = "#11283a"
    default_style = ""
    styles: typ.ClassVar = {  # ty: ignore[invalid-attribute-override]  # Pygments declares its class map without ClassVar.
        Text: "#edf6ff",
        Comment: "#bed0de",
        Comment.Preproc: "#7a9ffa",
        Error: "#fe536c",
        Generic: "#edf6ff",
        Keyword: "#7a9ffa",
        Name: "#edf6ff",
        Name.Attribute: "#7a9ffa",
        Name.Builtin: "#63ebf4",
        Name.Class: "#63ebf4",
        Name.Function: "#63ebf4",
        Name.Function.Magic: "#7a9ffa",
        Name.Namespace: "#bed0de",
        String: "#38f49d",
        String.Doc: "#bed0de",
        Number: "#38f49d",
        Operator: "#bed0de",
        Punctuation: "#bed0de",
    }
