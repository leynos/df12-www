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
    for token, spec in StilyagiStyle.styles.items():
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
            root_rule = f".stilyagi-syntax {{ color: var({declared[owner]}); }}"
            continue
        # Compound tokens yield space-separated classes (e.g. "s s-Doc")
        # which must chain into one compound selector.
        selectors[owner].append(".stilyagi-syntax ." + ".".join(css_class.split()))
    return selectors, root_rule


def build_css() -> str:
    """Build the generated CSS block from the Stilyagi style.

    Pygments emits the most specific token class it has — ``c1`` for a
    single-line comment, ``kn`` for an import keyword — while a style
    declares broad categories such as ``Comment`` and ``Keyword`` and lets
    the subtypes inherit. Emitting a rule only for each declared token would
    therefore leave most of the classes that actually appear in the markup
    unstyled, so each declared colour is emitted for its whole subtree.
    """
    formatter = HtmlFormatter(style=StilyagiStyle, cssclass="stilyagi-syntax")
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
