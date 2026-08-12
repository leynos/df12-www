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
from scripts.pygments_css import token_rules

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
CSS_CLASS = "stilyagi-syntax"
VARIABLE_PREFIX = "--stilyagi-syntax-"
#: Stilyagi's mono face is lighter, so bold goes the whole way.
BOLD_WEIGHT = "700"


def build_css() -> str:
    """Build the generated CSS block from the Stilyagi style."""
    formatter = HtmlFormatter(style=StilyagiStyle, cssclass=CSS_CLASS)
    variables, rules = token_rules(
        formatter,
        StilyagiStyle,
        CSS_CLASS,
        VARIABLE_PREFIX,
        BOLD_WEIGHT,
    )

    lines = [
        BEGIN,
        "",
        ":root {",
        *variables,
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
