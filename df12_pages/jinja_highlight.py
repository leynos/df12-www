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

Where the wrapper is itself the horizontal scroller it is emitted with
``tabindex="0"``, because a scrolling region has to be reachable from the
keyboard; see :data:`SCROLLING_CSS_CLASSES`.

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

#: Wrapper classes that are themselves the horizontal scroller, and so have to
#: be reachable from the keyboard.
#:
#: A region that scrolls but cannot be focused is unusable without a pointer,
#: and axe reports it as ``scrollable-region-focusable``. Which element scrolls
#: is a stylesheet decision, so the answer differs by sub-site. Episodic and
#: Stilyagi wrap each block in their own ``.code-scroll`` region, which carries
#: the scroll, the ``tabindex``, and an accessible name; their inner wrapper is
#: sized to the content and never scrolls, so making it focusable would only
#: add a tab stop that goes nowhere. Netsuke's ``hm-syntax`` has no such
#: wrapper and scrolls itself, so it is the element that needs the attribute.
SCROLLING_CSS_CLASSES = frozenset({DEFAULT_CSS_CLASS})


def _make_focusable(markup: str, css_class: str) -> str:
    """Add ``tabindex="0"`` to the wrapper Pygments opened *markup* with.

    Pygments offers no way to put an attribute on the wrapper, so it is added
    to the rendered string. The opening tag is matched in full rather than
    patched with a regular expression, so a change to what Pygments emits
    fails loudly here instead of silently leaving the region unfocusable.

    Parameters
    ----------
    markup
        The formatter's output, which begins with the wrapper's opening tag.
    css_class
        The wrapper class the formatter was configured with.

    Returns
    -------
    str
        *markup* with the attribute added to its opening tag.

    Raises
    ------
    TemplateRuntimeError
        If *markup* does not begin with the expected opening tag.

    Examples
    --------
    >>> _make_focusable('<div class="hm-syntax"><pre>x</pre></div>', "hm-syntax")
    '<div class="hm-syntax" tabindex="0"><pre>x</pre></div>'
    """
    opening = f'<div class="{css_class}">'
    if not markup.startswith(opening):
        message = (
            f"expected Pygments to open its output with {opening!r}; "
            f"it starts {markup[: len(opening)]!r}"
        )
        raise TemplateRuntimeError(message)
    replacement = f'<div class="{css_class}" tabindex="0">'
    return replacement + markup[len(opening) :]


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
        rendered = highlight(source, lexer, formatter)
        if css_class in SCROLLING_CSS_CLASSES:
            rendered = _make_focusable(rendered, css_class)
        return Markup(rendered)  # noqa: S704 -- Pygments escapes the untrusted source text


__all__ = ["DEFAULT_CSS_CLASS", "SCROLLING_CSS_CLASSES", "HighlightExtension"]
