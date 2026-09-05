"""The folds that make Tailwind v4's notation read as v3's.

v4 reports the same rendering in a different vocabulary: a transition list
with members v3 never named, an infinite corner radius where v3 wrote
9999px, a bottom margin where v3 put a top one. Each fold here maps both
notations to one value so that only a change to the page survives a diff,
along with the strip of run-to-run noise a value can carry.
"""

from __future__ import annotations

import re
import typing as typ

# The origin the harness serves on, port and all, as it appears inside a
# computed `url()`. Chromium resolves `background-image` against the document,
# so an inline `style="background-image: url(/netsuke/assets/x.jpg)"` is
# reported with the loopback port the capture happened to be given — a new
# one per run, since the default asks the kernel for a free port.
_LOOPBACK_ORIGIN = re.compile(r"http://127\.0\.0\.1:\d+")

# The uid Plotly mints for a chart on every render — six hex digits from a
# random seed — as it appears in the ids of the chart's clip paths, defs and
# legend, and in the `clip-path: url("#clip…")` that references them. The
# docs' security page draws one such chart, and each capture would otherwise
# report the whole chart as renamed.
_PLOTLY_UID = re.compile(r"\b(clip|topdefs-|defs-|legend)[0-9a-f]{6}")

# Members of a `transition-property` list that Tailwind v4 adds and v3 did
# not — v4's `transition-colors` names `outline-color` and the gradient stops,
# and its `transition-transform` names the individual transform properties.
# Nothing on the site transitions an outline, a gradient, or a bare
# `translate`, so the two lists describe the same behaviour; dropping the
# members from both sides lets them compare equal.
# `-webkit-text-decoration-color` is v3's prefixed duplicate of
# `text-decoration-color`.
_TRANSITION_NOISE = frozenset(
    {
        "outline-color",
        "--tw-gradient-from",
        "--tw-gradient-via",
        "--tw-gradient-to",
        "-webkit-text-decoration-color",
        "translate",
        "scale",
        "rotate",
    }
)

# A pixel length. Used to read margins and to cap radii.
_PX = re.compile(r"(-?\d+(?:\.\d+)?(?:e[+-]?\d+)?)px")

# The radius at which a corner is a semicircle whatever the box. Tailwind v3's
# `rounded-full` was `9999px`; v4's is `calc(infinity * 1px)`, which Chromium
# reports as `3.35544e+07px`. Both are "as round as it gets".
_FULL_RADIUS = 9999.0


def _canonical_transition(value: str) -> str:
    """Drop the members of a transition list that only one Tailwind knew.

    Parameters
    ----------
    value
        A computed ``transition-property``.

    Returns
    -------
    str
        The list without the members in :data:`_TRANSITION_NOISE`.
    """
    kept = [part for part in value.split(", ") if part not in _TRANSITION_NOISE]
    return ", ".join(kept)


def _capped_radius(value: str) -> str:
    """Read any radius past a semicircle as the same radius.

    Parameters
    ----------
    value
        A computed ``border-*-radius``.

    Returns
    -------
    str
        The value with every pixel length at or beyond :data:`_FULL_RADIUS`
        replaced by it.
    """

    def cap(match: re.Match[str]) -> str:
        length = float(match.group(1))
        return f"{_FULL_RADIUS:g}px" if length >= _FULL_RADIUS else match.group(0)

    return _PX.sub(cap, value)


def _incidental_text(value: str) -> str:
    """Strip the run-to-run noise a string value can carry.

    Parameters
    ----------
    value
        A computed style value, or an id.

    Returns
    -------
    str
        The value with the loopback port and any Plotly uid removed.
    """
    return _PLOTLY_UID.sub(r"\1", _LOOPBACK_ORIGIN.sub("http://127.0.0.1", value))


# The physical margins, each with the logical name Chromium reports beside it
# in a left-to-right document, and the parent gap that sits on the same axis.
_MARGIN_AXES = (
    ("top", "bottom", "margin-block-start", "margin-block-end", "row-gap"),
    ("left", "right", "margin-inline-start", "margin-inline-end", "column-gap"),
)


def _pixels(value: str | None) -> float | None:
    """Read a computed length as pixels, or ``None`` if it is not one.

    Parameters
    ----------
    value
        A computed margin or gap, or ``None`` when the node did not report
        one — which under the preflight means zero, since every element the
        preflight touches reports its zeroed margin as a diff from the
        user-agent default.

    Returns
    -------
    float or None
        The length in pixels, or ``None`` for ``auto``, a percentage, or
        anything else that is not a bare pixel length.
    """
    if value is None or value == "normal":
        return 0.0
    match = _PX.fullmatch(value)
    return float(match.group(1)) if match else None


def _fold_sibling_margins(
    children: list[dict[str, typ.Any]], parent_style: dict[str, typ.Any]
) -> None:
    """Rewrite each child's margins as the gaps between it and its siblings.

    Tailwind v3's ``space-y-*`` put a top margin on every child but the first;
    v4 puts a bottom margin on every child but the last. The children sit in
    exactly the same places, and every one of them reports a different
    margin. The same holds for ``space-x-*``, and for a ``gap-*`` on the
    parent standing in for either. What a reader sees is the space between
    two siblings, so that is what is compared: a child's gap before it is its
    own leading margin plus the previous sibling's trailing one plus the
    parent's gap on that axis, and likewise after. A margin that really
    changes still changes a gap.

    Parameters
    ----------
    children
        A node's normalized children, modified in place. A child whose margin
        on an axis is not a pixel length — ``auto``, a percentage — keeps its
        margins on that axis as they were.
    parent_style
        The parent's normalized styles, from which any ``row-gap`` or
        ``column-gap`` is read, and removed once a child's gap has absorbed
        it. A gap that folds into nothing — no children, a child whose
        margins are not pixel lengths, a gap that is not one itself — stays
        on the parent, where a change to it is still a change.
    """
    for before, after, logical_before, logical_after, gap_key in _MARGIN_AXES:
        gap = _pixels(parent_style.get(gap_key))
        if gap is None:
            continue
        folded = False
        leading = [
            _pixels(child["styleDiff"].get(f"margin-{before}")) for child in children
        ]
        trailing = [
            _pixels(child["styleDiff"].get(f"margin-{after}")) for child in children
        ]
        for index, child in enumerate(children):
            own_leading, own_trailing = leading[index], trailing[index]
            if own_leading is None or own_trailing is None:
                continue
            previous = trailing[index - 1] if index else 0.0
            following = leading[index + 1] if index + 1 < len(children) else 0.0
            if previous is None or following is None:
                continue
            folded = True
            style = child["styleDiff"]
            for key in (
                f"margin-{before}",
                f"margin-{after}",
                logical_before,
                logical_after,
            ):
                style.pop(key, None)
            gap_before = own_leading + previous + (gap if index else 0.0)
            gap_after = (
                own_trailing + following + (gap if index + 1 < len(children) else 0.0)
            )
            # A zero gap is what an absent margin already meant, so it is
            # left unsaid, as the margin would have been.
            if gap_before:
                style[f"gap-before-{before}"] = f"{gap_before:g}px"
            if gap_after:
                style[f"gap-after-{after}"] = f"{gap_after:g}px"
        if folded:
            parent_style.pop(gap_key, None)
