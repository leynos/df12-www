"""Utilities for rendering markdown and syntax-highlighted code snippets."""

from __future__ import annotations

import re
import typing as typ
from html import escape

from markdown import Markdown
from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

if typ.TYPE_CHECKING:
    from markdown.extensions import Extension
else:  # pragma: no cover - type-checking fallback
    Extension = typ.Any

CODE_BLOCK_PATTERN = re.compile(r"```([A-Za-z0-9_+#.-]+)?[^\n]*\n(.*?)```", re.DOTALL)
FENCED_INDENT_PATTERN = re.compile(r"^[ ]{1,3}([`~]{3,})", re.MULTILINE)
FENCE_LABEL_PATTERN = re.compile(
    r"^([`~]{3,})([A-Za-z0-9_+#.-]+)?(,[^\r\n]+)$", re.MULTILINE
)
CODEHILITE_OPEN_TAG = re.compile(r'<div class="codehilite">')


class HtmlContentRenderer:
    """Render markdown and code snippets with consistent styling."""

    def __init__(
        self, pygments_style: str = "monokai", link_extension: Extension | None = None
    ) -> None:
        """Initialize a renderer with optional pygments style and link extension.

        Parameters
        ----------
        pygments_style : str, optional
            Name of the Pygments style used for syntax highlighting. Defaults to
            ``"monokai"``.
        link_extension : Extension, optional
            Markdown extension used when rewriting links; pass ``None`` to skip
            link rewriting.
        """
        self.pygments_style = pygments_style
        self._formatter = HtmlFormatter(style=pygments_style, cssclass="codehilite")
        self._link_extension = link_extension

    @property
    def stylesheet(self) -> str:
        """Return the CSS used for highlighted code blocks."""
        return self._formatter.get_style_defs(".codehilite")

    def markdown(self, text: str) -> str:
        """Render markdown into HTML using the configured extensions."""
        normalized = self._normalize_fenced_blocks(text)
        if not normalized.strip():
            return ""
        extensions: list[Extension | str] = [
            "fenced_code",
            "codehilite",
            "tables",
            "sane_lists",
        ]
        if self._link_extension:
            extensions.append(self._link_extension)
        md = Markdown(
            extensions=extensions,
            extension_configs={
                "codehilite": {
                    "linenums": False,
                    "guess_lang": False,
                    "css_class": "codehilite",
                    "pygments_style": self.pygments_style,
                }
            },
        )
        html = md.convert(normalized)
        return self._annotate_codehilite(html, normalized)

    def code_block(self, code: str, language: str | None = None) -> str:
        """Render ``code`` into highlighted HTML with an optional language tag.

        Parameters
        ----------
        code : str
            Source snippet to highlight.
        language : str, optional
            Pygments lexer name; defaults to ``"text"`` when not provided or
            when the lexer lookup fails.

        Returns
        -------
        str
            HTML containing the highlighted block with ``data-language``
            metadata applied.
        """
        lang = language or "text"
        try:
            lexer = get_lexer_by_name(lang)
        except ClassNotFound:
            lexer = get_lexer_by_name("text")
        html = highlight(code, lexer, self._formatter)
        return self._attach_language_attribute(html, lang)

    def _annotate_codehilite(self, html: str, source_markdown: str) -> str:
        """Attach language metadata to each highlighted block in converted markdown."""
        languages = [
            match.group(1) or "text"
            for match in CODE_BLOCK_PATTERN.finditer(source_markdown)
        ]
        if not languages:
            return html
        lang_iter = iter(languages)

        def _repl(match: re.Match[str]) -> str:
            lang = next(lang_iter, "text")
            return (
                f'<div class="codehilite" data-language="{escape(lang, quote=True)}">'
            )

        return CODEHILITE_OPEN_TAG.sub(_repl, html, len(languages))

    @staticmethod
    def _attach_language_attribute(html: str, language: str) -> str:
        """Add a single language attribute to an already highlighted block."""
        safe_lang = escape(language or "text", quote=True)

        def _repl(match: re.Match[str]) -> str:
            return f'<div class="codehilite" data-language="{safe_lang}">'

        return CODEHILITE_OPEN_TAG.sub(_repl, html, 1)

    @staticmethod
    def _normalize_fenced_blocks(text: str) -> str:
        without_indent = FENCED_INDENT_PATTERN.sub(r"\1", text)

        def _strip_labels(match: re.Match[str]) -> str:
            fence, language, _extras = match.groups()
            label = language or ""
            return f"{fence}{label}"

        return FENCE_LABEL_PATTERN.sub(_strip_labels, without_indent)


__all__ = ["CODE_BLOCK_PATTERN", "HtmlContentRenderer"]
