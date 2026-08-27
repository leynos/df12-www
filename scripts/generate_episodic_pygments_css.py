"""Regenerate the ``.episodic-syntax`` Pygments rules in ``syntax.css``.

Mirrors the Netsuke and Stilyagi generators and reuses the shared
``scripts.pygments_css`` token-grouping logic. Pygments emits the most specific
class it holds for a token, so a rule per declared token would leave most
classes that actually appear in the markup unstyled.

Run from any directory with::

    uv run python scripts/generate_episodic_pygments_css.py
"""

from __future__ import annotations

from pathlib import Path

from pygments.formatters.html import HtmlFormatter

from df12_pages.episodic_highlighting import EpisodicStyle
from scripts.pygments_css import token_rules

REPO_ROOT = Path(__file__).resolve().parent.parent
STYLESHEET = REPO_ROOT / "src/static/episodic/assets/styles/syntax.css"

CSS_CLASS = "episodic-syntax"
VARIABLE_PREFIX = "--episodic-syntax-"
#: The subsite's mono face is IBM Plex Mono, whose medium reads as emphasis
#: without the weight jump a full bold introduces at this size.
BOLD_WEIGHT = "600"

HEADER = """/* Syntax highlighting for build-time Pygments output.
 *
 * GENERATED FILE - do not edit by hand. Regenerate with
 * `uv run python scripts/generate_episodic_pygments_css.py` after changing
 * df12_pages/episodic_highlighting.py.
 *
 * Colours come from the Episodic signal palette and are checked at a minimum
 * 4.5:1 against the code ground. Markup comes from the parent generator's
 * `{% highlight %}` tag, which emits token classes and no attributes, so the
 * scroll region and its label are supplied by the template wrapper.
 */
"""


def build_css() -> str:
    """Build the tracked CSS contract for Episodic syntax highlighting.

    Returns
    -------
    str
        The complete deterministic stylesheet, including token variables,
        the keyboard-reachable code-scroll region and every rule emitted from
        :class:`df12_pages.episodic_highlighting.EpisodicStyle`.
    """
    formatter = HtmlFormatter(style=EpisodicStyle, cssclass=CSS_CLASS)
    variables, rules = token_rules(
        formatter,
        EpisodicStyle,
        CSS_CLASS,
        VARIABLE_PREFIX,
        BOLD_WEIGHT,
    )

    lines = [
        HEADER,
        ":root {",
        *variables,
        "}",
        "",
        "/* Pygments emits no attributes, so the keyboard-reachable scroll",
        "   region is the wrapper the code_block macro supplies. */",
        ".code-scroll {",
        "  /* Stop long lines propagating min-content width up the grid and",
        "     widening the page on narrow viewports. */",
        "  contain: inline-size;",
        "  overflow-x: auto;",
        "}",
        "",
        f".{CSS_CLASS} {{",
        "  /* The ground is painted across the full scroll extent rather than",
        "     the visible width, so a scrolled block has no bare edge. */",
        "  width: max-content;",
        "  min-width: 100%;",
        "  box-sizing: border-box;",
        "  background: var(--surface-inset);",
        "}",
        "",
        f".{CSS_CLASS} pre {{",
        "  margin: 0;",
        "  padding: var(--space-4);",
        "  font-family: var(--font-machine);",
        "  font-size: 0.85rem;",
        "  line-height: 1.6;",
        "}",
        "",
        f".{CSS_CLASS} code {{",
        "  font-size: inherit;",
        "  word-break: normal;",
        "}",
        "",
        *rules,
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    """Write the generated stylesheet when it has changed."""
    css = build_css()
    current = STYLESHEET.read_text(encoding="utf-8") if STYLESHEET.is_file() else ""
    if current != css:
        STYLESHEET.parent.mkdir(parents=True, exist_ok=True)
        STYLESHEET.write_text(css, encoding="utf-8")
        print(f"{STYLESHEET.name} updated")
    else:
        print(f"{STYLESHEET.name} unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
