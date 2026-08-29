"""Shared pieces for the browser-driven Weaver suites.

The page list, the viewports, the axe waivers, and the small helpers that read
things back out of `agent-browser`. Kept here so the two suites that drive the
browser share one definition of what they are driving it over, and so neither
file grows past what one sitting can hold.
"""

from __future__ import annotations

import json
import re
import typing as typ
from pathlib import Path

import pytest

from df12_pages.config import load_site_config

if typ.TYPE_CHECKING:
    import collections.abc as cabc

REPO_ROOT = Path(__file__).resolve().parents[2]


def _weaver_config() -> typ.Any:  # noqa: ANN401 - SubSiteConfig is not exported
    """Load the Weaver sub-site's configuration, through the generator's own loader.

    `df12_pages.config.load_site_config` is what the generator reads this file
    with, so it is what these tests read it with too: parsing the YAML here
    separately would let the two drift, and the loader already validates the
    shape and raises `SiteConfigError` on a malformed one.

    Returns
    -------
    SubSiteConfig
        The `weaver` entry, with `content_pages` and `shared_content_refs`
        already parsed.
    """
    return load_site_config(REPO_ROOT / "config" / "pages.yaml").sites["weaver"]


def _published_pages() -> tuple[str, ...]:
    """List every Weaver page, from the config the generator itself reads.

    A hand-picked few would leave the rest unchecked, and the pages most
    likely to go unnoticed are exactly the ones nobody would think to pick:
    the three legal pages, which no Weaver template of their own renders, and
    the design-language page, which exists to display the palette. Taking the
    list from `config/pages.yaml` means a page added there is covered without
    anyone remembering to add it here.

    The config is used rather than the published tree because parametrization
    happens at collection, before the fixture that builds the tree has run.
    `test_the_published_tree_holds_exactly_the_pages_checked_here` asserts the
    two agree, so a config that has drifted from the build is a failure rather
    than a silent gap.

    Returns
    -------
    tuple of str
        Paths relative to ``/weaver/``, home first and the rest sorted.
    """
    weaver = _weaver_config()
    slugs = [page.output_slug for page in weaver.content_pages]
    slugs.extend(weaver.shared_content_refs)
    return ("", *sorted(f"{slug}/" for slug in slugs))


def _shared_content() -> frozenset[str]:
    """Name the pages rendered from shared content rather than a Weaver template.

    The three legal pages get the sub-site's chrome but none of its
    illustration, so an icon count of zero is what they should have.

    Returns
    -------
    frozenset of str
        Paths relative to ``/weaver/``.
    """
    return frozenset(f"{name}/" for name in _weaver_config().shared_content_refs)


PAGES = _published_pages()
SHARED_CONTENT = _shared_content()

# 360 is the narrowest viewport the design targets and the one that puts the
# sidebar off-canvas; 1440 is the width it was drawn against.
MOBILE_WIDTH, MOBILE_HEIGHT = 360, 800
DESKTOP_WIDTH, DESKTOP_HEIGHT = 1440, 900
VIEWPORTS = (
    ("mobile", MOBILE_WIDTH, MOBILE_HEIGHT),
    ("desktop", DESKTOP_WIDTH, DESKTOP_HEIGHT),
)

# The start of the HTTP error range. Named so the comparison below is not a
# bare number.
HTTP_ERROR = 400

# What the two layouts are distinguished by, measured the same way at both
# widths so the swap is one comparison rather than two descriptions.
#
# The drawer toggle has no markup of its own: `mobile-nav.js` builds it and
# gives it this id, so finding it also proves the script ran.
LAYOUT = (
    "JSON.stringify((() => {"
    "const toggle = document.querySelector('#mobile-nav-toggle');"
    "const link = document.querySelector('.weaver-nav-link');"
    "const box = link ? link.getBoundingClientRect() : null;"
    "return {toggle: toggle ? toggle.getBoundingClientRect().width > 0 : false,"
    "sidebar: box ? box.width > 0 && box.right > 0 : false,"
    "page: document.documentElement.scrollWidth,"
    "viewport: window.innerWidth};"
    "})())"
)

# WCAG 2.0 A and AA, which is the conformance level the sub-site claims.
AXE_TAGS = "wcag2a,wcag2aa"

# Contrast failures that are known, recorded, and somebody else's decision.
#
# `pages/safety.jinja`'s Operational Guidance labels were changed to the status
# tokens at review's request, over a stated contrast objection; the panel
# composites to #254675 and the labels measure 4.16:1 and 2.52:1 against it,
# both under the 4.5:1 that 12px bold needs. The remedy is lift variants of the
# status tokens remapped on the dark-surface selector `src/styles/weaver/
# panels.css` already uses for `text-accent-ink`, which is a palette change and
# so a decision rather than a fix. See the decision log in
# `docs/execplans/weaver-daisy-migration.md`.
#
# Keyed by page and CSS class so it waives those two labels and nothing else: a
# contrast failure anywhere else on the same page still fails. Each entry is
# also asserted to still fire, so the waiver cannot outlive the defect.
ACCEPTED = {
    ("safety/", "color-contrast", "text-status-ok"),
    ("safety/", "color-contrast", "text-status-error"),
}

TOOL_TIMEOUT_SECONDS = 120

# One class token inside an axe target selector. axe escapes the characters
# Tailwind puts in a class name, so `hover:bg-primary/5` arrives as
# `.hover\\:bg-primary\\/5` and an escape has to be consumed as a unit.
CLASS_TOKEN = re.compile(r"\.((?:\\.|[A-Za-z0-9_-])+)")


CASES = [
    pytest.param(page, width, height, id=f"{name}-{page or 'home'}")
    for page in PAGES
    for name, width, height in VIEWPORTS
]


def _open(
    drive: cabc.Callable[..., str], served: str, page: str, width: int, height: int
) -> None:
    """Size the viewport, then load one Weaver page into it.

    The order matters: a page loaded before the resize lays out at the old
    width, and the media queries this is checking would report the wrong
    layout.
    """
    drive("set", "viewport", str(width), str(height))
    drive("network", "requests", "--clear")
    drive("open", f"{served}/weaver/{page}")


def _evaluate(drive: cabc.Callable[..., str], expression: str) -> typ.Any:  # noqa: ANN401 - the caller decides what the page returns
    """Run an expression in the page and return its decoded result."""
    raw = drive("eval", expression).strip()
    return json.loads(json.loads(raw)) if raw.startswith('"') else json.loads(raw)


def _requests(drive: cabc.Callable[..., str]) -> list[dict[str, typ.Any]]:
    """Return every request the browser made since the log was last cleared."""
    payload = json.loads(drive("network", "requests", "--json"))
    return payload["data"]["requests"]


def _violations(drive: cabc.Callable[..., str]) -> list[dict[str, typ.Any]]:
    """Run axe over the current page and return its determinate failures.

    Axe reports a third state besides pass and fail: ``incomplete``, for
    checks it could not decide. Most of this sub-site's contrast checks land
    there, because the panels sit on a paper texture and a gradient and axe
    will not guess at a background it cannot resolve to one colour. Those are
    not failures and are not treated as any.
    """
    payload = json.loads(drive("a11y", "--tags", AXE_TAGS, "--json"))
    return payload["data"]["violations"]


def _classes(node: dict[str, typ.Any]) -> set[str]:
    """Return the class names named in an axe failure's target selector.

    A waiver has to match a whole class, not a substring of the selector.
    `"text-status-ok" in ".text-status-okay"` is true, and so is
    `"text-status-ok" in '[href$="text-status-ok/"]'`; either would waive a
    failure nobody decided to accept. Comparing against the parsed tokens
    makes the match exact.
    """
    target = " ".join(str(part) for part in node["target"])
    return {
        # `\:` and `\/` are one character each once the selector is read as
        # a selector rather than as text.
        re.sub(r"\\(.)", r"\1", token)
        for token in CLASS_TOKEN.findall(target)
    }


def _accepted(page: str, rule: str, node: dict[str, typ.Any]) -> bool:
    """Say whether one axe failure is a recorded exception for this page."""
    classes = _classes(node)
    return any(
        page == accepted_page and rule == accepted_rule and marker in classes
        for accepted_page, accepted_rule, marker in ACCEPTED
    )
