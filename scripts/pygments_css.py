"""Turn a Pygments style into CSS rules that cover the classes it emits.

Both sub-sites that highlight code at build time — Netsuke through
``HimotoshiStyle`` and Stilyagi through ``StilyagiStyle`` — need the same
translation, and it is not the obvious one. Pygments emits the most
specific class it holds for a token: ``c1`` for a single-line comment,
``s2`` for a double-quoted string, ``mi`` for an integer. A style declares
broad categories such as ``Comment`` and ``Literal.String`` and lets the
subtypes inherit. Emitting one rule per declared token therefore leaves
most of the classes that actually appear in the markup unstyled, and the
omission is invisible until someone reads the page: the affected tokens
render in the block's default colour rather than no colour at all.

:func:`token_rules` closes that gap by grouping every token in the
resolved style under the nearest ancestor the style declares, and
emitting that ancestor's colour for the whole group. What differs between
the two sub-sites is only naming and weight, so those are parameters; the
surrounding chrome — backgrounds, padding, media queries — stays in each
generator, which is where the sites genuinely diverge.
"""

from __future__ import annotations

import typing as typ

if typ.TYPE_CHECKING:
    from pygments.formatters.html import HtmlFormatter
    from pygments.style import Style


def variable_name(token: object, prefix: str) -> str:
    """Derive a CSS variable name from a Pygments token type.

    The bare ``Token`` type has no dotted tail, so it becomes ``text``.
    """
    joined = "-".join(str(token).split(".")[1:]).lower() or "text"
    return f"{prefix}{joined.replace('_', '-')}"


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


def _declared_colours(
    style: type[Style],
    prefix: str,
) -> tuple[dict[object, str], list[str]]:
    """Parse the style's specs into variables, keyed by declared token.

    Returns
    -------
    tuple
        The variable name per declared token, and the ``:root`` declarations
        in declaration order. Tokens whose spec carries no colour are
        skipped: they contribute no variable and inherit their colour from
        their nearest declared ancestor.
    """
    declared: dict[object, str] = {}
    variables: list[str] = []
    for token, spec in style.styles.items():
        colour = next((w for w in spec.split() if w.startswith("#")), "")
        if not colour:
            continue
        var = variable_name(token, prefix)
        declared[token] = var
        variables.append(f"  {var}: {colour};")
    return declared, variables


def _resolved_extras(
    formatter: HtmlFormatter,
    declared: dict[object, str],
    bold_weight: str,
) -> dict[object, str]:
    """Return the non-colour declarations (italic, bold) per declared token.

    These come from the formatter's *resolved* style rather than from the
    raw spec strings, because Pygments resolves a token by copying its
    parent's flags and then applying only the words the child restates. A
    subtype that overrides just the colour still inherits its ancestor's
    ``italic``: ``Comment.Preproc`` is declared as a bare colour but is
    italic, because ``Comment`` is. Reading the spec strings instead would
    silently drop that.
    """
    extras_for: dict[object, str] = {}
    for token, ndef in formatter.style:
        if token not in declared:
            continue
        extras: list[str] = []
        if ndef["italic"]:
            extras.append("font-style: italic;")
        if ndef["bold"]:
            extras.append(f"font-weight: {bold_weight};")
        extras_for[token] = " ".join(extras)
    return extras_for


def _selectors_by_owner(
    formatter: HtmlFormatter,
    declared: dict[object, str],
    css_class: str,
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
        token_class = class_for(token).strip()
        if not token_class:
            # The bare Token type styles the block's default text colour.
            root_rule = f".{css_class} {{ color: var({declared[owner]}); }}"
            continue
        # Compound tokens yield space-separated classes (e.g. "s s-Doc")
        # which must chain into one compound selector.
        selectors[owner].append(f".{css_class} ." + ".".join(token_class.split()))
    return selectors, root_rule


def token_rules(
    formatter: HtmlFormatter,
    style: type[Style],
    css_class: str,
    prefix: str,
    bold_weight: str,
) -> tuple[list[str], list[str]]:
    """Build the ``:root`` variables and token rules for *style*.

    Parameters
    ----------
    formatter:
        An ``HtmlFormatter`` already bound to *style*; it supplies both the
        resolved token list and the token-to-class mapping.
    style:
        The style class whose ``styles`` mapping declares the colours.
    css_class:
        The wrapper class the rules hang off, such as ``hm-syntax``.
    prefix:
        The custom-property prefix, such as ``--netsuke-syntax-``.
    bold_weight:
        The ``font-weight`` a ``bold`` spec should produce. The two
        sub-sites differ here because their body faces do.

    Returns
    -------
    tuple
        The ``:root`` declarations and the rules, both in the style's own
        declaration order so the output stays stable across runs. Order
        matters beyond tidiness: a subtype's rule must follow its
        ancestor's to win at equal specificity, which holds as long as the
        style declares parents before children.
    """
    declared, variables = _declared_colours(style, prefix)
    extras_for = _resolved_extras(formatter, declared, bold_weight)
    selectors, root_rule = _selectors_by_owner(formatter, declared, css_class)

    rules: list[str] = []
    if root_rule:
        rules.append(root_rule)
    for token, var in declared.items():
        group = selectors[token]
        if not group:
            continue
        extra = extras_for.get(token, "")
        body = f"color: var({var});" + (f" {extra}" if extra else "")
        rules.append(",\n".join(sorted(group)) + f" {{ {body} }}")
    return variables, rules


__all__ = ["token_rules", "variable_name"]
