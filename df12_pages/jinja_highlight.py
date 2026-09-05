"""A Jinja ``{% highlight %}`` tag rendering code through Pygments.

Modelled on the ``jinja2-highlight`` package's tag, implemented in-house so
the formatter can emit the Himotoshi ``hm-syntax`` wrapper and so custom
lexers resolve without depending on an unmaintained package. Usage inside a
template::

    {% highlight 'netsuke' %}
    netsuke_version: "1.0.0"
    {% endhighlight %}

The body is dedented, leading and trailing blank lines are stripped, and the
result is rendered with :class:`pygments.formatters.html.HtmlFormatter`.
The wrapper CSS class defaults to ``hm-syntax``, styled in
``src/styles/netsuke/himotoshi.css``; a sub-site with its own
syntax palette names its own class as a second argument::

    {% highlight 'python', 'stilyagi-syntax' %}
    from stilyagi.rule import Rule
    {% endhighlight %}

Jinja lexes the tag body before this extension sees it, so source text that
itself contains Jinja syntax (every ``Netsukefile`` with ``{{ ins }}``
placeholders) must be wrapped in ``{% raw %}`` inside the tag::

    {% highlight 'netsuke' %}{% raw %}
    command: "{{ cc }} -c {{ ins }}"
    {% endraw %}{% endhighlight %}
"""

from __future__ import annotations

import functools
import textwrap
import typing as typ

from jinja2 import TemplateRuntimeError, nodes
from jinja2.ext import Extension
from markupsafe import Markup
from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

if typ.TYPE_CHECKING:
    from jinja2.parser import Parser

#: Wrapper class used when a template does not name one, kept for the Netsuke
#: sub-site whose stylesheet styles ``hm-syntax``.
DEFAULT_CSS_CLASS = "hm-syntax"


@functools.lru_cache(maxsize=16)
def _formatter(css_class: str) -> HtmlFormatter:
    """Return the formatter for a wrapper class.

    Formatter configuration is immutable and rendering is stateless, so one
    instance per wrapper class can be shared across every render.

    The class name reaches this function from a template expression, so it is
    bounded in practice — the repository uses two — but not by construction.
    A bounded cache keeps a template that passed a computed class from
    retaining a formatter per distinct value for the life of the process.
    """
    return HtmlFormatter(cssclass=css_class, wrapcode=True)


class HighlightExtension(Extension):
    """Add ``{% highlight '<lexer>'[, '<class>'] %} ... {% endhighlight %}``."""

    tags: typ.ClassVar[set[str]] = {"highlight"}

    def parse(self, parser: Parser) -> nodes.Node:
        """Parse the tag and defer rendering to :meth:`_render`."""
        lineno = next(parser.stream).lineno
        lexer_name = parser.parse_expression()
        if parser.stream.skip_if("comma"):
            css_class = parser.parse_expression()
        else:
            css_class = nodes.Const(DEFAULT_CSS_CLASS)
        body = parser.parse_statements(("name:endhighlight",), drop_needle=True)
        call = self.call_method("_render", [lexer_name, css_class])
        return nodes.CallBlock(call, [], [], body).set_lineno(lineno)

    def _render(
        self,
        lexer_name: str,
        css_class: str,
        caller: typ.Callable[[], str],
    ) -> Markup:
        """Highlight the block body with the named Pygments lexer."""
        source = textwrap.dedent(str(caller())).strip("\n")
        try:
            lexer = get_lexer_by_name(lexer_name)
        except ClassNotFound as exc:
            message = (
                f"{{% highlight {lexer_name!r} %}} names an unknown Pygments lexer"
            )
            raise TemplateRuntimeError(message) from exc
        formatter = _formatter(css_class)
        return Markup(highlight(source, lexer, formatter))  # noqa: S704 -- Pygments escapes the untrusted source text


__all__ = ["DEFAULT_CSS_CLASS", "HighlightExtension"]
