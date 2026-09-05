"""Shared pieces for the browser-driven Netsuke suites.

The Netsuke counterpart of :mod:`tests.support.weaver_browser`: the page list,
the viewports, and the expression that reads the layout back out of
``agent-browser``. What the two sub-sites share — sizing the viewport before
a load, decoding an ``eval`` result — is imported from the Weaver module
rather than restated, so a fix there reaches both suites.
"""

from __future__ import annotations

import typing as typ
from pathlib import Path

import pytest

from df12_pages.config import load_site_config
from tests.support.weaver_browser import (
    DESKTOP_HEIGHT,
    DESKTOP_WIDTH,
    MOBILE_HEIGHT,
    MOBILE_WIDTH,
    VIEWPORTS,
    _evaluate,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

REPO_ROOT = Path(__file__).resolve().parents[2]

# The first URL segment of every Netsuke page, and the key its configuration
# sits under in `config/pages.yaml`.
SITE = "netsuke"
BASE_PATH = f"/{SITE}/"

__all__ = [
    "BASE_PATH",
    "CASES",
    "DESKTOP_HEIGHT",
    "DESKTOP_WIDTH",
    "KNOWN_OVERFLOW",
    "LAYOUT",
    "MOBILE_HEIGHT",
    "MOBILE_WIDTH",
    "PAGES",
    "SHARED_CONTENT",
    "SITE",
    "STANDALONE",
    "_evaluate",
    "_open",
]


def _netsuke_config() -> typ.Any:  # noqa: ANN401 - SubSiteConfig is not exported
    """Load the Netsuke sub-site's configuration, through the generator's own loader.

    Returns
    -------
    SubSiteConfig
        The `netsuke` entry, with `content_pages` and `shared_content_refs`
        already parsed.
    """
    return load_site_config(REPO_ROOT / "config" / "pages.yaml").sites[SITE]


def _published_pages() -> tuple[str, ...]:
    """List every Netsuke page, from the config the generator itself reads.

    The config is used rather than the published tree because parametrization
    happens at collection, before the fixture that builds the tree has run.
    `test_the_published_tree_holds_exactly_the_netsuke_pages_checked_here`
    asserts the two agree.

    Returns
    -------
    tuple of str
        Paths relative to ``/netsuke/``, home first and the rest sorted.
    """
    netsuke = _netsuke_config()
    slugs = [page.output_slug for page in netsuke.content_pages]
    slugs.extend(netsuke.shared_content_refs)
    return ("", *sorted(f"{slug}/" for slug in slugs))


def _shared_content() -> frozenset[str]:
    """Name the pages rendered from shared content rather than a Netsuke template.

    Returns
    -------
    frozenset of str
        Paths relative to ``/netsuke/``.
    """
    return frozenset(f"{name}/" for name in _netsuke_config().shared_content_refs)


PAGES = _published_pages()
SHARED_CONTENT = _shared_content()

# Pages that render no chrome at all. `pages/icon-replacements.jinja` is a
# standalone reference sheet with its own `<head>` and no navbar, by design;
# it is checked for fitting the viewport and for nothing about navigation.
STANDALONE = frozenset({"icon-replacements/"})

# Pages that lay out wider than the narrowest viewport today, before the
# migration touched anything, keyed to the width each was measured at. The
# migration is meant to be inert, so it neither fixes nor worsens these; the
# waiver is asserted to still fire, so it cannot outlive the defect. See the
# decision log in `docs/execplans/netsuke-daisy-migration.md`.
KNOWN_OVERFLOW = {
    "design/": 607,
    "examples/batch-photo-processing/": 363,
    "examples/multi-format-documentation/": 372,
    "examples/visual-design-assets/": 385,
}

# What the two layouts are distinguished by, measured the same way at both
# widths so the swap is one comparison rather than two descriptions.
#
# The desktop navigation is the block of links inside `#navbar` that is
# `hidden md:block`; the drawer toggle is `#navbar-mobile-toggle`, which is
# `md:hidden` and which `mobile-nav.js` reveals — so finding it laid out also
# proves the script ran. The Docs link appears twice in the navbar, once in
# each layout, and the desktop one comes first in document order, so the
# first match is the one whose box says which layout is showing.
LAYOUT = (
    "JSON.stringify((() => {"
    "const toggle = document.querySelector('#navbar-mobile-toggle');"
    "const link = document.querySelector('#navbar a[href=\"/netsuke/docs/\"]');"
    "const box = link ? link.getBoundingClientRect() : null;"
    "return {toggle: toggle ? toggle.getBoundingClientRect().width > 0 : false,"
    "nav: box ? box.width > 0 && box.right > 0 : false,"
    "page: document.documentElement.scrollWidth,"
    "viewport: document.documentElement.clientWidth};"
    "})())"
)

CASES = [
    pytest.param(page, width, height, id=f"{name}-{page or 'home'}")
    for page in PAGES
    for name, width, height in VIEWPORTS
]


def _open(
    drive: cabc.Callable[..., str], served: str, page: str, width: int, height: int
) -> None:
    """Size the viewport, then load one Netsuke page into it.

    The order matters: a page loaded before the resize lays out at the old
    width, and the media queries this is checking would report the wrong
    layout.
    """
    drive("set", "viewport", str(width), str(height))
    drive("network", "requests", "--clear")
    drive("open", f"{served}{BASE_PATH}{page}")
