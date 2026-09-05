"""Regenerate the ``.hm-syntax`` Pygments rules in ``himotoshi.css``.

Reads the token colours from
:class:`df12_pages.highlighting.HimotoshiStyle`, exposes each as a
``--netsuke-syntax-*`` CSS variable, and rewrites the marked block in
``src/styles/netsuke/himotoshi.css``, the partial the Netsuke Tailwind
entrypoint compiles into ``public/netsuke/assets/css/himotoshi.css``. The
stylesheet path is
resolved relative to this script, so it may be run from any directory:

    uv run python scripts/generate_himotoshi_pygments_css.py

The script is idempotent: rerunning it without changing the style leaves the
stylesheet untouched.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from pygments.formatters.html import HtmlFormatter

from df12_pages.highlighting import HimotoshiStyle
from scripts.pygments_css import token_rules

STYLESHEET = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "styles"
    / "netsuke"
    / "himotoshi.css"
)
BEGIN = (
    "/* BEGIN generated himotoshi-pygments"
    " (scripts/generate_himotoshi_pygments_css.py) */"
)
END = "/* END generated himotoshi-pygments */"
CSS_CLASS = "hm-syntax"
VARIABLE_PREFIX = "--netsuke-syntax-"
#: Netsuke's mono face reads heavy, so bold stops at semibold.
BOLD_WEIGHT = "600"


def build_css() -> str:
    """Build the generated CSS block from the Himotoshi style."""
    formatter = HtmlFormatter(style=HimotoshiStyle, cssclass=CSS_CLASS)
    variables, rules = token_rules(
        formatter,
        HimotoshiStyle,
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
        f".{CSS_CLASS} {{",
        "  background: var(--netsuke-charcoal);",
        "  border-radius: 0.5rem;",
        "  /* Stop long code lines propagating min-content width up the",
        "     flex chain and widening the page on narrow viewports. */",
        "  contain: inline-size;",
        "  overflow-x: auto;",
        "}",
        "",
        f".{CSS_CLASS} pre {{",
        "  margin: 0;",
        "  padding: 1.25rem 1.5rem;",
        '  font-family: "JetBrains Mono", monospace;',
        "  font-size: 0.875rem;",
        "  line-height: 1.7;",
        "}",
        "",
        "/* Inside faux-window chrome the container already pads and colours. */",
        f".hm-faux-window__body .{CSS_CLASS},",
        f".hm-example-code-block .{CSS_CLASS},",
        f".hm-example-terminal__body .{CSS_CLASS} {{",
        "  background: transparent;",
        "  border-radius: 0;",
        "}",
        "",
        f".hm-faux-window__body .{CSS_CLASS} pre,",
        f".hm-example-code-block .{CSS_CLASS} pre,",
        f".hm-example-terminal__body .{CSS_CLASS} pre {{",
        "  padding: 0;",
        "}",
        "",
        "/* Small mobile: shrink the text and reclaim the gutter, so long",
        "   lines fit without horizontal scrolling as often. Where a block",
        "   sits in its own padded chrome the inset is applied twice, and the",
        "   second helping costs characters the line can ill afford once the",
        "   type has shrunk; only the pre's own padding goes, because the",
        "   chrome's gutter is what holds the code off the dark ground's",
        "   edge. The trailing inset stays so a scrolled line does not end",
        "   flush. Placed after the base rule above so equal specificity",
        "   resolves in this rule's favour. */",
        "@media (max-width: 459.98px) {",
        f"  .{CSS_CLASS} pre {{",
        "    font-size: 0.7rem;",
        "    padding-block: 0;",
        "    padding-left: 0;",
        "  }",
        "}",
        "",
        *rules,
        "",
        END,
    ]
    return "\n".join(lines)


def main() -> int:
    """Rewrite the marked block in the stylesheet."""
    css = STYLESHEET.read_text(encoding="utf-8")
    block = build_css()
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL)
    if pattern.search(css):
        updated = pattern.sub(lambda _match: block, css)
    else:
        updated = css.rstrip("\n") + "\n\n" + block + "\n"
    if updated != css:
        STYLESHEET.write_text(updated, encoding="utf-8")
        sys.stdout.write("himotoshi.css updated\n")
    else:
        sys.stdout.write("himotoshi.css unchanged\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
