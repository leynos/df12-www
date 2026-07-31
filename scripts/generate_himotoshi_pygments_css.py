"""Regenerate the ``.hm-syntax`` Pygments rules in ``himotoshi.css``.

Reads the token colours from
:class:`df12_pages.highlighting.HimotoshiStyle`, exposes each as a
``--netsuke-syntax-*`` CSS variable, and rewrites the marked block in
``public/netsuke/assets/css/himotoshi.css``. The stylesheet path is resolved
relative to this script, so it may be run from any directory:

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

STYLESHEET = (
    Path(__file__).resolve().parent.parent
    / "public"
    / "netsuke"
    / "assets"
    / "css"
    / "himotoshi.css"
)
BEGIN = (
    "/* BEGIN generated himotoshi-pygments"
    " (scripts/generate_himotoshi_pygments_css.py) */"
)
END = "/* END generated himotoshi-pygments */"


def _variable_name(token: object) -> str:
    """Derive a CSS variable name from a Pygments token type."""
    joined = "-".join(str(token).split(".")[1:]).lower() or "text"
    return f"--netsuke-syntax-{joined.replace('_', '-')}"


def build_css() -> str:
    """Build the generated CSS block from the Himotoshi style."""
    formatter = HtmlFormatter(style=HimotoshiStyle, cssclass="hm-syntax")
    # Pygments has no public token-to-class API.
    class_for = formatter._get_css_classes

    variables: list[str] = []
    rules: list[str] = []
    for token, spec in HimotoshiStyle.styles.items():
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
                extras.append("font-weight: 600;")
        if not colour:
            continue
        variables.append(f"  {var}: {colour};")
        if css_class:
            extra = " ".join(extras)
            # Compound tokens yield space-separated classes (e.g. "p p-Indicator")
            # which must chain into one compound selector.
            selector = "." + ".".join(css_class.split())
            rules.append(
                f".hm-syntax {selector} {{ color: var({var});"
                f"{' ' + extra if extra else ''} }}"
            )
        else:
            # The bare Token type styles the block's default text colour.
            rules.append(f".hm-syntax {{ color: var({var}); }}")

    lines = [
        BEGIN,
        "",
        ":root {",
        *variables,
        "}",
        "",
        ".hm-syntax {",
        "  background: var(--netsuke-charcoal);",
        "  border-radius: 0.5rem;",
        "  /* Stop long code lines propagating min-content width up the",
        "     flex chain and widening the page on narrow viewports. */",
        "  contain: inline-size;",
        "  overflow-x: auto;",
        "}",
        "",
        ".hm-syntax pre {",
        "  margin: 0;",
        "  padding: 1.25rem 1.5rem;",
        '  font-family: "JetBrains Mono", monospace;',
        "  font-size: 0.875rem;",
        "  line-height: 1.7;",
        "}",
        "",
        "/* Inside faux-window chrome the container already pads and colours. */",
        ".hm-faux-window__body .hm-syntax,",
        ".hm-example-code-block .hm-syntax,",
        ".hm-example-terminal__body .hm-syntax {",
        "  background: transparent;",
        "  border-radius: 0;",
        "}",
        "",
        ".hm-faux-window__body .hm-syntax pre,",
        ".hm-example-code-block .hm-syntax pre,",
        ".hm-example-terminal__body .hm-syntax pre {",
        "  padding: 0;",
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
