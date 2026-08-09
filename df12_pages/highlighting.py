"""Netsuke Pygments syntaxes and the Himotoshi highlighting style.

Two lexers cover the Netsuke sub-site's code blocks:

- ``netsuke``: YAML with embedded Jinja expressions, as written in a
  ``Netsukefile``. A thin subclass of Pygments' stock ``YamlJinjaLexer``.
- ``netsuke-console``: shell sessions where lines beginning with a ``$``
  prompt are commands (a trailing backslash continues the command on the
  next line) and all other lines are program output. A thin subclass of
  Pygments' stock ``BashSessionLexer``, which already implements those
  semantics.

Both render through :class:`HimotoshiStyle`, whose colours are accessible
tints (WCAG AA, at least 4.5:1 against the charcoal block background) of
the Himotoshi design-language palette. The style's values are mirrored by
the generated ``.hm-syntax`` rules in
``src/static/netsuke/assets/css/himotoshi.css``; regenerate those with
``scripts/generate_himotoshi_pygments_css.py`` after changing this module.

The lexers and style are registered with Pygments through the
``pygments.lexers`` and ``pygments.styles`` entry points declared in
``pyproject.toml``, so ``get_lexer_by_name("netsuke")`` works anywhere in
the pipeline.
"""

from __future__ import annotations

import typing as typ

from pygments.lexers.shell import BashSessionLexer
from pygments.lexers.templates import YamlJinjaLexer
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


class NetsukeLexer(YamlJinjaLexer):
    """YAML with embedded Jinja, as used in a ``Netsukefile``."""

    name = "Netsuke"
    aliases: typ.ClassVar[list[str]] = ["netsuke", "netsukefile"]
    filenames: typ.ClassVar[list[str]] = ["Netsukefile", "*.netsuke.yml"]
    mimetypes: typ.ClassVar[list[str]] = []


class NetsukeConsoleLexer(BashSessionLexer):
    """Shell session: ``$``-prefixed commands, backslash continuation, output."""

    name = "Netsuke console"
    aliases: typ.ClassVar[list[str]] = ["netsuke-console"]
    filenames: typ.ClassVar[list[str]] = []
    mimetypes: typ.ClassVar[list[str]] = []


class HimotoshiStyle(Style):
    """Pygments style drawn from the Himotoshi palette.

    Every colour is an accessible tint of a Himotoshi hue, checked at a
    minimum 4.5:1 contrast ratio against the ``--netsuke-charcoal``
    background used by the sub-site's code windows.
    """

    name = "himotoshi"
    background_color = "#2e2a25"
    highlight_color = "#3a352e"

    styles: typ.ClassVar[dict[typ.Any, str]] = {
        Token: "#e5ddd0",  # stone-light: default text
        Comment: "italic #a39a8e",  # tint of charcoal-light
        Comment.Preproc: "#e0b45c",  # Jinja {% ... %} markers; tint of amber
        Keyword: "#dba396",  # tint of vermillion
        Operator: "#d1c7b8",  # stone
        Punctuation: "#d1c7b8",  # stone
        Punctuation.Indicator: "#d1c7b8",
        Name.Tag: "#a8c3e0",  # YAML keys; tint of indigo-light
        Name.Variable: "#e0b45c",  # Jinja variables; tint of amber
        Name.Function: "#e0b45c",
        Name.Builtin: "#e8d5b5",  # boxwood: shell builtins
        Literal.String: "#8fbf9f",  # tint of matcha
        Literal.String.Escape: "#e0b45c",
        Number: "#d9b36a",  # tint of amber
        Generic.Prompt: "bold #8fbf9f",  # the $ prompt; tint of matcha
        Generic.Output: "#b8b0a5",  # programme output; tint of stone
        Generic.Error: "#dba396",
        Error: "#dba396",
    }


__all__ = ["HimotoshiStyle", "NetsukeConsoleLexer", "NetsukeLexer"]
