"""Browser checks for the published wireframe sub-site.

Contrast and overflow are properties of the rendered page rather than of the
markup, so these tests read them back from ``agent-browser`` against the
built ``public/`` tree. They use the shared ``served`` and ``drive``
fixtures, so the suite relies on the site build the ``built_site`` fixture
runs.

The accessibility bar is the one AGENTS.md sets: zero axe violations against
WCAG 2.0 A and AA, at a phone width and a desktop width. Both are checked
because a code region only reports as an unreachable scroller once it
actually scrolls, and because the hero scene drops its labels below 640px.
The sub-site carries no waivers, so any failure is a failure.
"""

from __future__ import annotations

import typing as typ

import pytest

from tests.support.weaver_browser import _evaluate, _violations

if typ.TYPE_CHECKING:
    import collections.abc as cabc

pytestmark = pytest.mark.playwright

# The first URL segment of every wireframe page.
BASE_PATH = "/wireframe/"

# Every width is measured at this height, as the rendered-page checks in
# AGENTS.md set it.
HEIGHT = 900

# The narrowest width the site supports, a phone, and a desktop.
NARROWEST = 320
PHONE = 390
DESKTOP = 1440

# Every page the sub-site publishes, legal notices included.
PAGES = (
    "",
    "getting-started/",
    "guides/",
    "guides/routing/",
    "guides/codecs/",
    "guides/middleware/",
    "guides/streaming/",
    "guides/large-messages/",
    "guides/client/",
    "guides/testing/",
    "guides/production/",
    "architecture/",
    "examples/",
    "roadmap/",
    "yard/",
    "privacy-policy/",
    "terms-of-use/",
    "code-of-conduct/",
)

# The document's width against the viewport's, and the first few elements
# that reach past it, leaving out anything inside a region that scrolls on
# purpose and the content of a closed disclosure, such as the mobile menu,
# which Chrome lays out without painting.
LAYOUT = """JSON.stringify((() => {
  const viewport = document.documentElement.clientWidth;
  const offenders = [...document.querySelectorAll('body *')]
    .filter((el) => el.getBoundingClientRect().right > viewport + 1)
    .filter((el) => !el.closest('.wf-code__scroll, .wf-table-scroll'))
    .filter((el) => !el.closest('details:not([open]) > :not(summary)'))
    .slice(0, 5)
    .map((el) => el.tagName + '.' + String(el.className).slice(0, 40));
  return {page: document.documentElement.scrollWidth, viewport, offenders};
})())"""


def _open(drive: cabc.Callable[..., str], served: str, page: str, width: int) -> None:
    """Size the viewport, then load one wireframe page into it.

    The order matters: a page loaded before the resize lays out at the old
    width, and the media queries would report the wrong layout.
    """
    drive("set", "viewport", str(width), str(HEIGHT))
    drive("open", f"{served}{BASE_PATH}{page}")


@pytest.mark.timeout(900)
@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("page", [pytest.param(p, id=p or "home") for p in PAGES])
def test_a_wireframe_page_meets_wcag_aa(
    drive: cabc.Callable[..., str], served: str, page: str, width: int
) -> None:
    """Every page passes axe over WCAG 2.0 A and AA, at both widths."""
    _open(drive, served, page, width)
    failures = [
        f"{violation['id']} on {node['target']}"
        for violation in _violations(drive)
        for node in violation["nodes"]
    ]
    assert not failures, f"{BASE_PATH}{page} at {width}px fails axe: {failures}"


@pytest.mark.timeout(900)
@pytest.mark.parametrize("page", [pytest.param(p, id=p or "home") for p in PAGES])
def test_a_wireframe_page_fits_the_narrowest_phone(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """At 320px nothing but a code or table region scrolls sideways."""
    _open(drive, served, page, NARROWEST)
    layout = _evaluate(drive, LAYOUT)
    assert layout["page"] <= layout["viewport"], (
        f"{BASE_PATH}{page} lays out {layout['page']}px wide in a "
        f"{layout['viewport']}px viewport"
    )
    assert not layout["offenders"], (
        f"{BASE_PATH}{page} has elements past the viewport: {layout['offenders']}"
    )
