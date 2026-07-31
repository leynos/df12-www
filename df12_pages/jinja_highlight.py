"""A Jinja ``{% highlight %}`` tag rendering code through Pygments.

Modelled on the ``jinja2-highlight`` package's tag, implemented in-house so
the formatter can emit the Himotoshi ``hm-syntax`` wrapper and so custom
lexers resolve without depending on an unmaintained package. Usage inside a
template::

    {% highlight 'netsuke' %}
    netsuke_version: "1.0.0"
    {% endhighlight %}

The body is dedented, leading and trailing blank lines are stripped, and the
result is rendered with :class:`pygments.formatters.html.HtmlFormatter`
using the ``hm-syntax`` CSS class styled in
``public/netsuke/assets/css/himotoshi.css``.

Jinja lexes the tag body before this extension sees it, so source text that
itself contains Jinja syntax (every ``Netsukefile`` with ``{{ ins }}``
placeholders) must be wrapped in ``{% raw %}`` inside the tag::

    {% highlight 'netsuke' %}{% raw %}
    command: "{{ cc }} -c {{ ins }}"
    {% endraw %}{% endhighlight %}
"""

from __future__ import annotations

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

#: Shared formatter; its configuration is immutable and rendering is stateless.
_FORMATTER = HtmlFormatter(cssclass="hm-syntax", wrapcode=True)


class HighlightExtension(Extension):
    """Add ``{% highlight '<lexer>' %} ... {% endhighlight %}`` to Jinja."""

    tags: typ.ClassVar[set[str]] = {"highlight"}

    def parse(self, parser: Parser) -> nodes.Node:
        """Parse the tag and defer rendering to :meth:`_render`."""
        lineno = next(parser.stream).lineno
        lexer_name = parser.parse_expression()
        body = parser.parse_statements(("name:endhighlight",), drop_needle=True)
        call = self.call_method("_render", [lexer_name])
        return nodes.CallBlock(call, [], [], body).set_lineno(lineno)

    def _render(self, lexer_name: str, caller: typ.Callable[[], str]) -> Markup:
        """Highlight the block body with the named Pygments lexer."""
        source = textwrap.dedent(str(caller())).strip("\n")
        try:
            lexer = get_lexer_by_name(lexer_name)
        except ClassNotFound as exc:
            message = (
                f"{{% highlight {lexer_name!r} %}} names an unknown Pygments lexer"
            )
            raise TemplateRuntimeError(message) from exc
        return Markup(highlight(source, lexer, _FORMATTER))  # noqa: S704 -- Pygments escapes the untrusted source text


__all__ = ["HighlightExtension"]
