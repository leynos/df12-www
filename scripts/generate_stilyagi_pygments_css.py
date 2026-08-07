"""Regenerate the ``.stilyagi-syntax`` Pygments rules in ``syntax.css``.

Reads the token colours from
:class:`df12_pages.stilyagi_highlighting.StilyagiStyle`, exposes each as a
``--stilyagi-syntax-*`` CSS variable, and rewrites the marked block in
``src/static/stilyagi/assets/styles/syntax.css``. The stylesheet path is
resolved relative to this script, so it may be run from any directory:

    uv run python scripts/generate_stilyagi_pygments_css.py

This mirrors ``generate_himotoshi_pygments_css.py``, which does the same for
the Netsuke sub-site. The script is idempotent: rerunning it without changing
the style leaves the stylesheet untouched.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from pygments.formatters.html import HtmlFormatter

from df12_pages.stilyagi_highlighting import StilyagiStyle

STYLESHEET = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "static"
    / "stilyagi"
    / "assets"
    / "styles"
    / "syntax.css"
)
BEGIN = (
    "/* BEGIN generated stilyagi-pygments"
    " (scripts/generate_stilyagi_pygments_css.py) */"
)
END = "/* END generated stilyagi-pygments */"


def _variable_name(token: object) -> str:
    """Derive a CSS variable name from a Pygments token type."""
    joined = "-".join(str(token).split(".")[1:]).lower() or "text"
    return f"--stilyagi-syntax-{joined.replace('_', '-')}"


def build_css() -> str:
    """Build the generated CSS block from the Stilyagi style."""
    formatter = HtmlFormatter(style=StilyagiStyle, cssclass="stilyagi-syntax")
    # Pygments has no public token-to-class API.
    class_for = formatter._get_css_classes

    variables: list[str] = []
    rules: list[str] = []
    for token, spec in StilyagiStyle.styles.items():
        css_class = class_for(token).strip()
        var = _variable_name(token)
        colour = ""
        extras: list[str] = []
        for word in spec.split():
            if word.startswith("#"):
                colour = word
            elif word == "italic":
                extras.append("font-style: italic;")
            elif word == "bold":
                extras.append("font-weight: 700;")
        if not colour:
            continue
        variables.append(f"  {var}: {colour};")
        if css_class:
            extra = " ".join(extras)
            # Compound tokens yield space-separated classes (e.g. "s s-Doc")
            # which must chain into one compound selector.
            selector = "." + ".".join(css_class.split())
            rules.append(
                f".stilyagi-syntax {selector} {{ color: var({var});"
                f"{' ' + extra if extra else ''} }}"
            )
        else:
            # The bare Token type styles the block's default text colour.
            rules.append(f".stilyagi-syntax {{ color: var({var}); }}")

    lines = [
        BEGIN,
        "",
        ":root {",
        *variables,
        "}",
        "",
        "/* The scroll lives on a wrapper the template supplies, because a",
        "   scrollable region must be keyboard reachable and Pygments emits",
        "   the inner markup without attributes. Templates wrap the tag in",
        '   <div class="code-scroll" tabindex="0" role="region"> with a label. */',
        ".code-scroll {",
        "  /* Stop long code lines propagating min-content width up the",
        "     grid and widening the page on narrow viewports. */",
        "  contain: inline-size;",
        "  overflow-x: auto;",
        "  /* Pass a stretched height through to the block inside, so the ink",
        "     ground fills the column when the panel beside it is taller. */",
        "  display: flex;",
        "  flex-direction: column;",
        "}",
        "",
        "/* Matches the pre.code component this replaced: the ink ground and",
        "   the press-red rule down the left edge. The width pair keeps the",
        "   ground painted across the full scroll extent, not just the",
        "   visible width. */",
        ".stilyagi-syntax {",
        "  flex: 1;",
        "  background: var(--ink);",
        "  border-left: var(--rule-weight-3) solid var(--press-red);",
        "  width: max-content;",
        "  min-width: 100%;",
        "  box-sizing: border-box;",
        "}",
        "",
        ".stilyagi-syntax pre {",
        "  margin: 0;",
        "  padding: calc(var(--unit) * 2.5) calc(var(--unit) * 3);",
        "  font-family: var(--font-mono);",
        "  /* Matches .term, the diagnostic view set beside it; the pair read",
        "     as one specimen, and the author view then fits its column",
        "     without scrolling at desktop widths. */",
        "  font-size: 0.88rem;",
        "  line-height: 1.55;",
        "}",
        "",
        *rules,
        "",
        END,
    ]
    return "\n".join(lines)


def main() -> int:
    """Rewrite the marked block in the stylesheet."""
    css = STYLESHEET.read_text(encoding="utf-8") if STYLESHEET.exists() else ""
    block = build_css()
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL)
    if pattern.search(css):
        updated = pattern.sub(lambda _match: block, css)
    else:
        updated = (css.rstrip("\n") + "\n\n" if css.strip() else "") + block + "\n"
    if updated != css:
        STYLESHEET.parent.mkdir(parents=True, exist_ok=True)
        STYLESHEET.write_text(updated, encoding="utf-8")
        sys.stdout.write("syntax.css updated\n")
    else:
        sys.stdout.write("syntax.css unchanged\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
