"""Regenerate the ``.hm-syntax`` Pygments rules in ``himotoshi.css``.

Reads the token colours from
:class:`df12_pages.highlighting.HimotoshiStyle`, exposes each as a
``--netsuke-syntax-*`` CSS variable, and rewrites the marked block in
``src/static/netsuke/assets/css/himotoshi.css``. The stylesheet path is
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

STYLESHEET = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "static"
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


def _nearest_declared(token: object, declared: dict[object, str]) -> object | None:
    """Return the closest ancestor of *token* the style declares, if any.

    Pygments token types are not publicly typed, so the parent chain is
    walked with ``getattr``; the root ``Token`` has no parent, which ends
    the walk.
    """
    node: object | None = token
    while node is not None:
        if node in declared:
            return node
        node = getattr(node, "parent", None)
    return None


def _declared_colours() -> tuple[dict[object, str], list[str], dict[object, str]]:
    """Parse the style's specs into variables, keyed by declared token.

    Returns
    -------
    tuple
        The variable name per declared token, the ``:root`` declarations in
        declaration order, and the non-colour extras (italic, bold) per token.
        Tokens whose spec carries no colour are skipped: they contribute no
        variable and inherit from their nearest declared ancestor.
    """
    declared: dict[object, str] = {}
    variables: list[str] = []
    extras_for: dict[object, str] = {}
    for token, spec in HimotoshiStyle.styles.items():
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
        var = _variable_name(token)
        declared[token] = var
        extras_for[token] = " ".join(extras)
        variables.append(f"  {var}: {colour};")
    return declared, variables, extras_for


def _selectors_by_owner(
    formatter: HtmlFormatter,
    declared: dict[object, str],
) -> tuple[dict[object, list[str]], str]:
    """Group every token in the style under the ancestor it inherits from.

    Returns
    -------
    tuple
        The selectors owned by each declared token, and the rule for the
        block's default text colour, which the bare ``Token`` type carries
        and which has no class of its own.
    """
    # Pygments has no public token-to-class API.
    class_for = formatter._get_css_classes
    selectors: dict[object, list[str]] = {token: [] for token in declared}
    root_rule = ""
    for token, _ndef in formatter.style:
        owner = _nearest_declared(token, declared)
        if owner is None:
            continue
        css_class = class_for(token).strip()
        if not css_class:
            # The bare Token type styles the block's default text colour.
            root_rule = f".hm-syntax {{ color: var({declared[owner]}); }}"
            continue
        # Compound tokens yield space-separated classes (e.g. "p p-Indicator")
        # which must chain into one compound selector.
        selectors[owner].append(".hm-syntax ." + ".".join(css_class.split()))
    return selectors, root_rule


def build_css() -> str:
    """Build the generated CSS block from the Himotoshi style.

    Pygments emits the most specific token class it has — ``c1`` for a
    single-line comment, ``s2`` for a double-quoted string — while a style
    declares broad categories such as ``Comment`` and ``Literal.String`` and
    lets the subtypes inherit. Emitting a rule only for each declared token
    would therefore leave most of the classes that actually appear in the
    markup unstyled, so each declared colour is emitted for its whole
    subtree.
    """
    formatter = HtmlFormatter(style=HimotoshiStyle, cssclass="hm-syntax")
    declared, variables, extras_for = _declared_colours()
    # Declaration order is preserved throughout so the output stays stable.
    selectors, root_rule = _selectors_by_owner(formatter, declared)

    rules: list[str] = []
    if root_rule:
        rules.append(root_rule)
    for token, var in declared.items():
        group = selectors[token]
        if not group:
            continue
        extra = extras_for[token]
        body = f"color: var({var});" + (f" {extra}" if extra else "")
        rules.append(",\n".join(sorted(group)) + f" {{ {body} }}")

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
        "/* Small mobile: shrink terminal text so long lines fit without",
        "   horizontal scrolling as often. Placed after the base rule above so",
        "   equal specificity resolves in this rule's favour. */",
        "@media (max-width: 459.98px) {",
        "  .hm-syntax pre {",
        "    font-size: 0.7rem;",
        "  }",
        "}",
        "",
        "/* Reclaim the gutter at the narrowest widths: where a block sits in",
        "   its own padded chrome the inset is applied twice, and the second",
        "   helping costs characters the line can ill afford once the type has",
        "   shrunk. Only the pre's own padding goes — the chrome keeps its",
        "   gutter, which is what holds the code off the dark ground's edge.",
        "   The trailing inset stays so a scrolled line does not end flush. */",
        "@media (max-width: 460px) {",
        "  .hm-syntax pre {",
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
