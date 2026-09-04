"""Conventions the Netsuke markup and stylesheet have to keep.

Two utilities of the same kind on one element make the winner a source-order
accident, and a doubled selector in the partial is a fossil of the Play CDN
era, when a hand-written rule had to out-specify a utility to beat it. Both
are silent everywhere else.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_weaver_conventions import CLASS_ATTRIBUTE, FONT_SIZE

REPO_ROOT = Path(__file__).resolve().parents[1]
NETSUKE_TEMPLATES = REPO_ROOT / "templates" / "netsuke"
ENTRYPOINT = REPO_ROOT / "src" / "styles" / "netsuke.css"
PARTIAL = REPO_ROOT / "src" / "styles" / "netsuke" / "himotoshi.css"

# A class selector repeated against itself — `.hm-hero.hm-hero` — which only
# ever raised specificity. The Pygments generator writes `.p.p-Indicator`,
# an ancestor chain of two different classes, so the second occurrence has
# to end where the first did.
DOUBLED_SELECTOR = re.compile(r"(\.[A-Za-z_][\w-]*)\1(?![\w-])")

# The one place the partial is allowed to beat a utility: the phone-width
# full-bleed block, whose `!important` declarations are load-bearing. Found by
# its comment, since the same width heads two other media queries.
FULL_BLEED = "/* Full-bleed code and terminal panels on phone-width viewports."


def test_no_element_declares_two_font_sizes_at_once() -> None:
    """Two font-size utilities on one element make the winner a source-order accident.

    Only unprefixed utilities are counted. A responsive variant beside a base
    size — `text-sm md:text-base` — is the intended way to change size at a
    breakpoint, not a duplicate.
    """
    offenders: dict[str, list[str]] = {}
    for source in sorted(NETSUKE_TEMPLATES.rglob("*.jinja")):
        text = source.read_text(encoding="utf-8")
        for attribute in CLASS_ATTRIBUTE.finditer(text):
            value = attribute.group(1) or attribute.group(2) or ""
            sizes = [token for token in value.split() if FONT_SIZE.match(token)]
            if len(sizes) > 1:
                number = text.count("\n", 0, attribute.start()) + 1
                where = f"{source.relative_to(REPO_ROOT)}:{number}+{attribute.start()}"
                offenders[where] = sizes

    assert not offenders, (
        "these elements declare more than one font size, so which one applies "
        f"depends on the order the utilities happen to be written in: {offenders}"
    )


def test_the_partial_carries_no_doubled_selectors() -> None:
    """A selector repeated against itself is a fossil of the Play CDN era.

    `.hm-hero.hm-hero` and its like existed to out-specify a utility the CDN
    injected after the stylesheet. In the components layer a utility wins
    whatever the specificity, so the doubling does nothing — and a new one
    would be somebody reaching for the old trick instead of moving the
    utility into the component.
    """
    fossils = sorted(
        {
            match.group(0)
            for match in DOUBLED_SELECTOR.finditer(PARTIAL.read_text(encoding="utf-8"))
        }
    )
    assert not fossils, f"doubled selectors remain in {PARTIAL.name}: {fossils}"


def test_the_partial_is_imported_into_the_components_layer() -> None:
    """The hand-written rules sit below the utilities, where a utility wins."""
    entrypoint = ENTRYPOINT.read_text(encoding="utf-8")
    assert '@import "./netsuke/himotoshi.css" layer(components);' in entrypoint, (
        "himotoshi.css must be imported with layer(components); unlayered, it "
        "would beat every utility in the markup"
    )
    assert '@import "./netsuke/site-base.css" layer(base);' in entrypoint, (
        "the element defaults belong beside the preflight"
    )


def test_important_is_confined_to_the_full_bleed_block() -> None:
    """`!important` beats layer order; only the phone-width full-bleed may use it."""
    text = PARTIAL.read_text(encoding="utf-8")
    # The block's own comment names the flag; the region left out runs from
    # that comment to the media query's closing brace.
    start = text.index(FULL_BLEED)
    depth = 0
    end = start
    for index, char in enumerate(text[start:], start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = index
                break
    outside = text[:start] + text[end:]
    assert "!important" not in outside, (
        "an !important outside the full-bleed block beats the utilities in the "
        "markup; move the utility into the component instead"
    )


@pytest.mark.parametrize(
    ("selector", "doubled"),
    [
        (".hm-hero.hm-hero", True),
        (".hm-faux-window--card-bleed.hm-faux-window--card-bleed", True),
        (".p.p-Indicator", False),
        (".hm-syntax .p.p-Indicator", False),
        (".hm-rows > :not([hidden]) ~ :not([hidden])", False),
    ],
)
def test_the_doubled_selector_pattern_tells_a_fossil_from_a_chain(
    selector: str, *, doubled: bool
) -> None:
    """The Pygments block's `.p.p-…` chains must not read as fossils."""
    assert bool(DOUBLED_SELECTOR.search(selector)) is doubled, (
        f"{selector!r} should {'' if doubled else 'not '}read as a doubled selector"
    )
