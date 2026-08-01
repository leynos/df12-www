"""Utilities for rendering markdown and syntax-highlighted code snippets."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
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
MERMAID_BLOCK_PATTERN = re.compile(r"```mermaid[^\n]*\n(.*?)```", re.DOTALL)


class MermaidRenderer:
    """Compile Mermaid sources to inline SVG with a headless renderer.

    The renderer shells out to ``merman-cli`` (override the executable with
    the ``DF12_MERMAID_CLI`` environment variable). Failures are reported on
    stderr and return ``None`` so callers can fall back to a highlighted code
    block rather than aborting a build.
    """

    def __init__(self, executable: str | None = None) -> None:
        """Initialize the renderer.

        Parameters
        ----------
        executable : str, optional
            Mermaid CLI to invoke. Defaults to the ``DF12_MERMAID_CLI``
            environment variable, then ``"merman-cli"``.
        """
        self.executable = (
            executable or os.environ.get("DF12_MERMAID_CLI") or "merman-cli"
        )
        self._cache: dict[str, str | None] = {}

    def render(self, source: str) -> str | None:
        """Return inline SVG for ``source`` or ``None`` when rendering fails.

        Results are cached per source text, and the ``id`` attribute the CLI
        stamps on every SVG is rewritten to a content-derived value so several
        diagrams can share a page without colliding style scopes.
        """
        key = source.strip()
        if key in self._cache:
            return self._cache[key]
        svg = self._invoke(key)
        if svg is not None:
            unique = f"merman-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:12]}"
            svg = svg.replace('id="merman"', f'id="{unique}"').replace(
                "#merman", f"#{unique}"
            )
        self._cache[key] = svg
        return svg

    def _invoke(self, source: str) -> str | None:
        """Run the Mermaid CLI over ``source`` and capture the SVG output."""
        command = [self.executable, "-i", "-", "-o", "-", "-e", "svg"]
        try:
            proc = subprocess.run(  # noqa: S603 - fixed command, repo-controlled input
                command,
                input=source.encode("utf-8"),
                capture_output=True,
                timeout=120,
                check=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            detail = ""
            if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
                detail = f": {exc.stderr.decode('utf-8', 'replace').strip()[:500]}"
            print(
                f"warning: mermaid rendering failed ({exc.__class__.__name__}){detail}",
                file=sys.stderr,
            )
            return None
        return proc.stdout.decode("utf-8")


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
        self._mermaid = MermaidRenderer()

    @property
    def stylesheet(self) -> str:
        """Return the CSS used for highlighted code blocks."""
        return self._formatter.get_style_defs(".codehilite")

    def markdown(self, text: str) -> str:
        """Render markdown into HTML using the configured extensions.

        Mermaid fences are compiled to inline SVG figures at build time; a
        fence whose diagram fails to render falls back to a highlighted code
        block.
        """
        normalized = self._normalize_fenced_blocks(text)
        if not normalized.strip():
            return ""
        normalized, mermaid_figures = self._extract_mermaid_blocks(normalized)
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
        html = self._annotate_codehilite(html, normalized)
        return self._restore_mermaid_blocks(html, mermaid_figures)

    def _extract_mermaid_blocks(self, text: str) -> tuple[str, dict[str, str]]:
        """Swap renderable Mermaid fences for placeholder tokens.

        Returns the rewritten markdown plus a mapping of placeholder token to
        the rendered ``<figure>`` markup. Fences whose diagrams fail to render
        are left in place so they fall through to code highlighting.
        """
        figures: dict[str, str] = {}

        def _replace(match: re.Match[str]) -> str:
            svg = self._mermaid.render(match.group(1))
            if svg is None:
                return match.group(0)
            token = f"df12-mermaid-placeholder-{len(figures)}"
            figures[token] = f'<figure class="doc-mermaid">{svg}</figure>'
            return f"\n\n{token}\n\n"

        return MERMAID_BLOCK_PATTERN.sub(_replace, text), figures

    @staticmethod
    def _restore_mermaid_blocks(html: str, figures: dict[str, str]) -> str:
        """Replace placeholder tokens with their rendered Mermaid figures."""
        for token, figure in figures.items():
            wrapped = f"<p>{token}</p>"
            if wrapped in html:
                html = html.replace(wrapped, figure)
            else:  # pragma: no cover - defensive: token outside a paragraph
                html = html.replace(token, figure)
        return html

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


__all__ = ["CODE_BLOCK_PATTERN", "HtmlContentRenderer", "MermaidRenderer"]
