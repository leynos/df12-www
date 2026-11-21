"""Utilities for rendering markdown and syntax-highlighted code snippets."""

from __future__ import annotations

import dataclasses as dc
import hashlib
import os
import re
import subprocess
import sys
import typing as typ
from html import escape

from markdown import Markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.sane_lists import SaneListExtension
from markdown.extensions.tables import TableExtension
from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

from df12_pages.generator.link_rewriter import RelativeLinkExtension

if typ.TYPE_CHECKING:
    import collections.abc as cabc

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


@dc.dataclass(frozen=True)
class PreparedMarkdown:
    """Markdown whose Mermaid figures were compiled ahead of rendering.

    ``markdown`` holds placeholder tokens where renderable diagrams sat, and
    ``figures`` maps each token to the ``<figure>`` markup that replaces it
    once the document has been converted. A fence that failed to render is
    left in the markdown, so it falls through to code highlighting.

    ``link_ref`` is the git ref captured at preparation time for the
    document's relative links. Carrying it with the document keeps a retained
    document's links pointing at the tree that answered its own fetch, even
    after another document's fetch has been retargeted.
    """

    markdown: str
    figures: dict[str, str] = dc.field(default_factory=dict)
    link_ref: str | None = None


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
        self._executable = executable
        self._cache: dict[str, str | None] = {}

    @property
    def executable(self) -> str:
        """Return the CLI to invoke, reading the override only when needed.

        The environment is consulted per invocation so constructing a
        renderer is free of ambient configuration. A caller that wants a fixed
        command, such as a test, passes it to the constructor.
        """
        return self._executable or os.getenv("DF12_MERMAID_CLI") or "merman-cli"

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
        self,
        pygments_style: str = "monokai",
        link_extension: Extension | None = None,
        mermaid: MermaidRenderer | None = None,
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
        mermaid : MermaidRenderer, optional
            Renderer for fenced Mermaid diagrams. Tests inject one that fails
            if a path under test starts a subprocess.
        """
        self.pygments_style = pygments_style
        self._formatter = HtmlFormatter(style=pygments_style, cssclass="codehilite")
        self._link_extension = link_extension
        self._mermaid = mermaid or MermaidRenderer()

    @property
    def stylesheet(self) -> str:
        """Return the CSS used for highlighted code blocks."""
        return self._formatter.get_style_defs(".codehilite")

    def _configured_ref(self) -> str | None:
        """Return the git ref the link extension was configured with, if any."""
        if isinstance(self._link_extension, RelativeLinkExtension):
            return self._link_extension.ref
        return None

    def _link_extension_for(self, link_ref: str | None) -> Extension | None:
        """Return the link extension that rewrites links for ``link_ref``.

        The configured extension is reused when it already names the ref, and a
        fresh extension is built for a document whose fetch answered from a
        different one. Returning a new instance rather than mutating the shared
        extension keeps each prepared document bound to the ref that answered
        its own fetch.
        """
        extension = self._link_extension
        if not isinstance(extension, RelativeLinkExtension):
            return extension
        if link_ref is None or link_ref == extension.ref:
            return extension
        return RelativeLinkExtension(extension.repo, link_ref, extension.base_dir)

    def prepare_markdown(
        self, text: str, *, link_ref: str | None = None
    ) -> PreparedMarkdown:
        """Compile a document's Mermaid fences and rewrite them as placeholders.

        This is the step that may start the Mermaid CLI, so a caller that needs
        an I/O-free render runs it first and hands the result to
        :meth:`render_prepared`. A fence whose diagram fails to render is left
        in place, so it falls through to a highlighted code block.

        Parameters
        ----------
        text : str
            The document body as fetched.
        link_ref : str, optional
            Git ref the document's fetch answered from. A fetch that falls back
            to the branch answered from a different ref than the configured
            release pin, and the links inside the document then have to point
            into the tree it actually came from. ``None`` keeps the configured
            ref, which is right when the source was an explicit override with
            no ref to name. The ref is captured into the returned document, so
            a later retarget cannot change how this one renders.
        """
        effective_ref = link_ref if link_ref is not None else self._configured_ref()
        normalized = self._normalize_fenced_blocks(text)
        if not normalized.strip():
            return PreparedMarkdown("", link_ref=effective_ref)
        normalized, figures = self._extract_mermaid_blocks(normalized)
        return PreparedMarkdown(normalized, figures, link_ref=effective_ref)

    def render_prepared(self, prepared: PreparedMarkdown) -> str:
        """Convert already-prepared markdown to HTML without compiling fences."""
        return self._convert(prepared.markdown, prepared.figures, prepared.link_ref)

    def markdown(
        self,
        text: str,
        *,
        figures: cabc.Mapping[str, str] | None = None,
        link_ref: str | None = None,
    ) -> str:
        """Render markdown into HTML using the configured extensions.

        Mermaid fences are compiled to inline SVG figures at build time; a
        fence whose diagram fails to render falls back to a highlighted code
        block. When ``figures`` is supplied, ``text`` is markdown already
        prepared by :meth:`prepare_markdown` and no fence is compiled here.

        ``link_ref`` names the git ref relative links point into. Section
        markdown derived from a prepared document passes the ref that document
        captured, so every conversion of one document agrees on the tree it
        came from.
        """
        if figures is None:
            return self.render_prepared(self.prepare_markdown(text, link_ref=link_ref))
        return self._convert(text, figures, link_ref)

    def _convert(
        self,
        normalized: str,
        figures: cabc.Mapping[str, str],
        link_ref: str | None = None,
    ) -> str:
        """Convert prepared markdown and restore its Mermaid figures."""
        if not normalized.strip():
            return ""
        # Instances rather than names: naming an extension makes Python-Markdown
        # scan every installed distribution's ``entry_points.txt`` through
        # ``importlib.metadata`` to look the name up. Configuring instances
        # keeps that filesystem work out of a render.
        extensions: list[Extension | str] = [
            FencedCodeExtension(),
            CodeHiliteExtension(
                linenums=False,
                guess_lang=False,
                css_class="codehilite",
                pygments_style=self.pygments_style,
            ),
            TableExtension(),
            SaneListExtension(),
        ]
        link_extension = self._link_extension_for(link_ref)
        if link_extension:
            extensions.append(link_extension)
        md = Markdown(extensions=extensions)
        html = md.convert(normalized)
        html = self._annotate_codehilite(html, normalized)
        return self._restore_mermaid_blocks(html, figures)

    def _extract_mermaid_blocks(self, text: str) -> tuple[str, dict[str, str]]:
        """Swap renderable Mermaid fences for placeholder tokens.

        Returns the rewritten markdown plus a mapping of placeholder token to
        the rendered ``<figure>`` markup. Fences whose diagrams fail to render
        are left in place so they fall through to code highlighting.
        """
        figures: dict[str, str] = {}

        def _replace(match: re.Match[str]) -> str:
            """Render one Mermaid fence to a placeholder, or keep it on failure."""
            svg = self._mermaid.render(match.group(1))
            if svg is None:
                return match.group(0)
            token = f"df12-mermaid-placeholder-{len(figures)}"
            figures[token] = f'<figure class="doc-mermaid">{svg}</figure>'
            return f"\n\n{token}\n\n"

        return MERMAID_BLOCK_PATTERN.sub(_replace, text), figures

    @staticmethod
    def _restore_mermaid_blocks(html: str, figures: cabc.Mapping[str, str]) -> str:
        """Replace placeholder tokens with their rendered Mermaid figures.

        A token standing alone in a paragraph replaces the paragraph, since a
        ``<figure>`` may not sit inside a ``<p>``. The alternation lists longer
        tokens first, so one token that prefixes another -- ``-1`` of ``-10``
        -- can never consume part of the longer one when a section holds only
        some of the document's diagrams.
        """
        if not figures:
            return html
        alternation = "|".join(
            re.escape(token) for token in sorted(figures, key=len, reverse=True)
        )
        pattern = re.compile(rf"<p>({alternation})</p>|({alternation})")

        def _replace(match: re.Match[str]) -> str:
            """Return the figure for whichever alternative matched."""
            token = match.group(1) or match.group(2)
            return figures[token]

        return pattern.sub(_replace, html)

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
            """Stamp the next detected language onto a codehilite opening tag."""
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
            """Rewrite a codehilite opening tag with the fixed language attribute."""
            return f'<div class="codehilite" data-language="{safe_lang}">'

        return CODEHILITE_OPEN_TAG.sub(_repl, html, 1)

    @staticmethod
    def _normalize_fenced_blocks(text: str) -> str:
        """Strip fence indentation and comma-separated info-string extras."""
        without_indent = FENCED_INDENT_PATTERN.sub(r"\1", text)

        def _strip_labels(match: re.Match[str]) -> str:
            """Keep the fence and language from a fence line, dropping the extras."""
            fence, language, _extras = match.groups()
            label = language or ""
            return f"{fence}{label}"

        return FENCE_LABEL_PATTERN.sub(_strip_labels, without_indent)


__all__ = [
    "CODE_BLOCK_PATTERN",
    "HtmlContentRenderer",
    "MermaidRenderer",
    "PreparedMarkdown",
]
