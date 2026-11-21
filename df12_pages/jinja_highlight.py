"""Render MiniJinja highlight filter blocks through Pygments.

:func:`highlight_code` is the public entry point: :mod:`df12_pages.templating`
registers it as the ``highlight`` filter, so a template's
``{% filter highlight(lexer, css_class) %}`` block reaches it. The remaining
helpers are private to the rendering path.
"""

from __future__ import annotations

import functools
import textwrap

from markupsafe import Markup
from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

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
    RuntimeError
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
        raise RuntimeError(message)
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


def highlight_code(
    value: str, lexer_name: str, css_class: str = DEFAULT_CSS_CLASS
) -> Markup:
    """Render a MiniJinja filter block with Pygments.

    Parameters
    ----------
    value : str
        Rendered block body, including the contents of any included sample.
    lexer_name : str
        Pygments lexer alias.
    css_class : str
        Class for the wrapper that carries the site's syntax palette.

    Returns
    -------
    Markup
        Highlighted HTML with a keyboard stop when the wrapper scrolls.
    """
    source = textwrap.dedent(value).strip("\n")
    try:
        lexer = get_lexer_by_name(lexer_name)
    except ClassNotFound as exc:
        message = f"highlight({lexer_name!r}) names an unknown Pygments lexer"
        raise RuntimeError(message) from exc
    formatter = _formatter(css_class)
    rendered = highlight(source, lexer, formatter)
    if css_class in SCROLLING_CSS_CLASSES:
        rendered = _make_focusable(rendered, css_class)
    return Markup(rendered)  # noqa: S704 -- Pygments escapes the untrusted source text
