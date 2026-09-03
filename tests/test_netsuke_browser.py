"""What every published Netsuke page does when a browser loads it.

The chrome's two layouts — the link list at desktop widths and the drawer
below the tablet breakpoint — and whether the document fits the viewport it
was given. These are the properties the daisyUI migration must not disturb,
and they are asserted from the browser because a computed-style diff cannot
tell whether a page that laid out wider than 360px did so before as well.

Marked ``playwright``, so `-m "not playwright"` deselects the lot while
iterating on something else.
"""

from __future__ import annotations

import typing as typ
from pathlib import Path

import pytest

from tests.support.netsuke_browser import (
    BASE_PATH,
    DESKTOP_HEIGHT,
    DESKTOP_WIDTH,
    KNOWN_OVERFLOW,
    LAYOUT,
    MOBILE_HEIGHT,
    MOBILE_WIDTH,
    PAGES,
    SITE,
    STANDALONE,
    _evaluate,
    _open,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_NETSUKE = REPO_ROOT / "public" / SITE

pytestmark = pytest.mark.playwright


@pytest.mark.timeout(900)
@pytest.mark.parametrize("page", PAGES)
def test_a_netsuke_page_fits_a_phone(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """At 360 the toggle is the navigation and the link list is hidden.

    Getting that backwards leaves a page with no way to navigate at all. A
    page wider than the viewport is the other classic mobile failure: the code
    panels scroll on purpose and are allowed to, but the document is not.

    Four pages already overflow at this width and are waived by name; the
    waiver asserts the overflow is still there, so fixing one of them fails
    this test until the entry is removed, and worsening one fails it outright.
    """
    _open(drive, served, page, MOBILE_WIDTH, MOBILE_HEIGHT)
    narrow = _evaluate(drive, LAYOUT)

    if page not in STANDALONE:
        assert narrow["toggle"], (
            f"{BASE_PATH}{page} has no drawer toggle at {MOBILE_WIDTH}px, so the "
            "menu it hides cannot be opened"
        )
        assert not narrow["nav"], (
            f"{BASE_PATH}{page} still lays out the desktop link list at "
            f"{MOBILE_WIDTH}px, where it does not fit"
        )
    if (known := KNOWN_OVERFLOW.get(page)) is not None:
        assert narrow["viewport"] < narrow["page"] <= known, (
            f"{BASE_PATH}{page} was waived at {known}px wide but now lays out at "
            f"{narrow['page']}px; if it fits, drop it from KNOWN_OVERFLOW, and "
            "if it grew, that is a regression"
        )
        return
    assert narrow["page"] <= narrow["viewport"], (
        f"{BASE_PATH}{page} lays out {narrow['page']}px wide in a "
        f"{narrow['viewport']}px viewport, so the whole page scrolls sideways"
    )


@pytest.mark.timeout(900)
@pytest.mark.parametrize("page", PAGES)
def test_a_netsuke_page_lays_out_its_nav_on_a_desktop(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """The wide layout's half of the swap: the link list, and no toggle."""
    _open(drive, served, page, DESKTOP_WIDTH, DESKTOP_HEIGHT)
    wide = _evaluate(drive, LAYOUT)

    if page not in STANDALONE:
        assert wide["nav"], f"{BASE_PATH}{page} has no link list at {DESKTOP_WIDTH}px"
        assert not wide["toggle"], (
            f"{BASE_PATH}{page} shows the drawer toggle at {DESKTOP_WIDTH}px, "
            "beside the link list it stands in for"
        )
    assert wide["page"] <= wide["viewport"], (
        f"{BASE_PATH}{page} lays out {wide['page']}px wide in a "
        f"{wide['viewport']}px viewport"
    )


def test_the_published_tree_holds_exactly_the_netsuke_pages_checked_here(
    built_site: Path,
) -> None:
    """The page list is taken from the config, so it can drift from the build.

    Parametrization happens at collection, before anything is built, which is
    why the list cannot simply be read off the published tree. A page
    generated but not listed here would go unchecked, and one listed but not
    generated would make every other test fail on a 404.
    """
    del built_site  # the fixture is the build; the tree it returns is Weaver's
    published = sorted(
        f"{path.parent.relative_to(PUBLIC_NETSUKE).as_posix()}/".removeprefix("./")
        for path in PUBLIC_NETSUKE.rglob("index.html")
    )
    assert published == sorted(PAGES), (
        "config/pages.yaml and the published tree disagree about which Netsuke "
        f"pages exist. Published: {published}. Checked here: {sorted(PAGES)}"
    )
