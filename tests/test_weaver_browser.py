"""What every published Weaver page does when a browser loads it.

Seventeen pages at two viewports: what each fetches, whether it meets WCAG AA
once colours are composited rather than guessed at, which nav link it marks
current, whether its icons carry artwork, and whether the sidebar gives way to
the drawer at 360px.

Marked ``playwright``, so `-m "not playwright"` deselects the lot while
iterating on something else.
"""

from __future__ import annotations

import typing as typ
from pathlib import Path

import pytest

from tests.support.weaver_browser import (
    ACCEPTED,
    CASES,
    DESKTOP_HEIGHT,
    DESKTOP_WIDTH,
    HTTP_ERROR,
    LAYOUT,
    MOBILE_HEIGHT,
    MOBILE_WIDTH,
    PAGES,
    SHARED_CONTENT,
    _accepted,
    _classes,
    _evaluate,
    _open,
    _requests,
    _violations,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

REPO_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.playwright


@pytest.mark.timeout(900)
@pytest.mark.parametrize(("page", "width", "height"), CASES)
def test_a_weaver_page_is_self_contained(
    drive: cabc.Callable[..., str], served: str, page: str, width: int, height: int
) -> None:
    """Self-containment is the migration's point, asserted from the browser.

    The static check on the delivered markup cannot see a URL a stylesheet
    builds, an image a script inserts, or a font a ``@font-face`` resolves. It
    also cannot see a request that failed, and a page that fetched nothing at
    all would satisfy "nothing remote" vacuously. All three are read back from
    the browser's own log.
    """
    _open(drive, served, page, width, height)
    requests = _requests(drive)
    where = f"/weaver/{page} at {width}px"

    assert requests, f"{where} reported no requests at all, not even the page"

    remote = sorted(
        {
            request["url"]
            for request in requests
            if not request["url"].startswith((served, "data:", "about:"))
        }
    )
    assert not remote, f"{where} fetched from another origin: {remote}"

    failed = sorted(
        {
            f"{request['status']} {request['url'].removeprefix(served)}"
            for request in requests
            if request.get("status", 0) >= HTTP_ERROR
        }
    )
    assert not failed, f"{where} has subresources that failed: {failed}"

    kinds = {request["resourceType"] for request in requests}
    assert {"Document", "Stylesheet", "Font", "Script"} <= kinds, (
        f"{where} fetched only {sorted(kinds)}; the compiled stylesheet, the "
        "webfonts and the drawer script should all be served from here"
    )


@pytest.mark.timeout(900)
@pytest.mark.parametrize(("page", "width", "height"), CASES)
def test_a_weaver_page_meets_wcag_aa(
    drive: cabc.Callable[..., str], served: str, page: str, width: int, height: int
) -> None:
    """Contrast is a property of the rendered page, not of the class names.

    ``text-base-content`` says nothing about what it composites to through an
    ``opacity-60`` on a cream panel; only a browser can say, and what it said
    was 3.33:1. This check is what found that, and the thirty-one scrollable
    code panels no keyboard could reach.
    """
    _open(drive, served, page, width, height)

    unexpected = [
        f"{violation['id']} on {node['target']}: "
        f"{node['failureSummary'].splitlines()[-1].strip()}"
        for violation in _violations(drive)
        for node in violation["nodes"]
        if not _accepted(page, violation["id"], node)
    ]
    assert not unexpected, (
        f"/weaver/{page} at {width}px fails accessibility checks: {unexpected}"
    )


@pytest.mark.timeout(600)
def test_the_recorded_contrast_exceptions_are_still_real(
    drive: cabc.Callable[..., str], served: str
) -> None:
    """A waiver that outlives its defect quietly stops checking anything.

    If the status tokens are given lift variants on dark surfaces — the remedy
    the decision log names — these two stop failing, and this fails instead so
    the exception is removed with them rather than left behind.
    """
    _open(drive, served, "safety/", DESKTOP_WIDTH, DESKTOP_HEIGHT)

    waived = {marker for _page, _rule, marker in ACCEPTED}
    fired = {
        (violation["id"], marker)
        for violation in _violations(drive)
        for node in violation["nodes"]
        for marker in waived & _classes(node)
    }
    expected = {(rule, marker) for _page, rule, marker in ACCEPTED}

    assert fired == expected, (
        "the accepted contrast exceptions for pages/safety.jinja no longer "
        f"match what the page does. Expected {sorted(expected)}, observed "
        f"{sorted(fired)}. If they now pass, drop them from ACCEPTED and from "
        "the decision log."
    )


@pytest.mark.timeout(900)
@pytest.mark.parametrize("page", PAGES)
def test_a_weaver_page_renders_its_chrome(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """The nav and the icons come from macros, so a miss is silent.

    At most one link may be current, and it has to point at somewhere this
    page actually is. Three shapes are legitimate and the check allows all
    three: the page's own href; an ancestor of it, since the three command
    sub-pages highlight the Commands section they belong to; and a fragment,
    since the design-language page reuses the nav classes for its own
    in-page anchors. Two current links would mean the companion macro handed
    down the wrong value, and none is correct only for a page the sidebar does
    not list — the three legal pages, where the macro returns an empty string.

    An unmapped icon renders the literal text ``UNKNOWN ICON``, and a macro
    that generated an empty body renders an ``<svg>`` with nothing in it.
    Neither shows up in a stylesheet diff. The legal pages are shared content
    with no icons of their own, so they are checked for rendering none badly
    rather than for rendering any.
    """
    _open(drive, served, page, DESKTOP_WIDTH, DESKTOP_HEIGHT)
    report = _evaluate(
        drive,
        "JSON.stringify({"
        "current: [...document.querySelectorAll('[aria-current=\"page\"]')]"
        ".map((a) => a.getAttribute('href')),"
        "listed: [...document.querySelectorAll('.weaver-nav-link')]"
        ".map((a) => a.getAttribute('href')),"
        "empty: [...document.querySelectorAll('svg')]"
        ".filter((s) => s.children.length === 0).length,"
        "total: document.querySelectorAll('svg').length,"
        "unknown: document.body.textContent.includes('UNKNOWN ICON')})",
    )

    own = f"/weaver/{page}"
    current = report["current"]
    assert len(current) <= 1, (
        f"/weaver/{page} marks {current} as current; at most one link can be"
    )
    if own in report["listed"]:
        assert current == [own], (
            f"/weaver/{page} is listed in the nav but marks {current} as the "
            f"current page rather than {[own]}"
        )
    else:
        assert all(href.startswith("#") or own.startswith(href) for href in current), (
            f"/weaver/{page} marks {current} as current, which is neither this "
            f"page, an ancestor section of it, nor an anchor within it"
        )

    if page not in SHARED_CONTENT:
        assert report["total"] > 0, f"/weaver/{page} rendered no icons at all"
    assert report["empty"] == 0, (
        f"/weaver/{page} has {report['empty']} icons with no artwork in them"
    )
    assert not report["unknown"], (
        f"/weaver/{page} names an icon the generated macro does not define"
    )


@pytest.mark.timeout(900)
@pytest.mark.parametrize("page", PAGES)
def test_a_weaver_page_fits_a_phone(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """At 360 the toggle is the navigation and the sidebar is off-canvas.

    Getting that backwards leaves a page with no way to navigate at all. A
    page wider than the viewport is the other classic mobile failure: the code
    panels scroll on purpose and are allowed to, but the document is not, and
    a stray fixed width makes every line of body text need a scroll to read.
    """
    _open(drive, served, page, MOBILE_WIDTH, MOBILE_HEIGHT)
    narrow = _evaluate(drive, LAYOUT)

    assert narrow["toggle"], (
        f"/weaver/{page} has no drawer toggle at {MOBILE_WIDTH}px, so the "
        "sidebar it hides cannot be opened"
    )
    assert not narrow["sidebar"], (
        f"/weaver/{page} still lays out the sidebar at {MOBILE_WIDTH}px, "
        "where it does not fit"
    )
    assert narrow["page"] <= narrow["viewport"], (
        f"/weaver/{page} lays out {narrow['page']}px wide in a "
        f"{narrow['viewport']}px viewport, so the whole page scrolls sideways"
    )


@pytest.mark.timeout(900)
@pytest.mark.parametrize("page", PAGES)
def test_a_weaver_page_lays_out_its_sidebar_on_a_desktop(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """The wide layout's half of the swap, which shares no chrome with the narrow."""
    _open(drive, served, page, DESKTOP_WIDTH, DESKTOP_HEIGHT)
    wide = _evaluate(drive, LAYOUT)

    assert wide["sidebar"], (
        f"/weaver/{page} has no sidebar navigation at {DESKTOP_WIDTH}px"
    )


def test_the_published_tree_holds_exactly_the_pages_checked_here(
    built_site: Path,
) -> None:
    """The page list is taken from the config, so it can drift from the build.

    Parametrization happens at collection, before anything is built, which is
    why the list cannot simply be read off the published tree. This is what
    stops that convenience from becoming a gap: a page generated but not
    listed here would go unchecked, and one listed but not generated would
    make every other test skip past it.
    """
    published = sorted(
        f"{path.parent.relative_to(built_site).as_posix()}/".removeprefix("./")
        for path in built_site.rglob("index.html")
    )
    assert published == sorted(PAGES), (
        "config/pages.yaml and the published tree disagree about which Weaver "
        f"pages exist. Published: {published}. Checked here: {sorted(PAGES)}"
    )
