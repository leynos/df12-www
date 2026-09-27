"""Browser checks for the published rstest-bdd sub-site.

Contrast, overflow, and the storybook's behaviour are properties of the
rendered page rather than of the markup, so these tests read them back from
``agent-browser`` against the built ``public/`` tree. They use the shared
``served`` and ``drive`` fixtures, so the suite relies on the site build the
``built_site`` fixture runs.

The accessibility bar is the one AGENTS.md sets: zero axe violations against
WCAG 2.0 A and AA, at a phone width and a desktop width. Both are checked
because a code region only reports as an unreachable scroller once it
actually scrolls. The sub-site carries no waivers, so any failure is a
failure.
"""

from __future__ import annotations

import typing as typ

import pytest

from tests.support.weaver_browser import _evaluate, _violations

if typ.TYPE_CHECKING:
    import collections.abc as cabc

pytestmark = pytest.mark.playwright

# The first URL segment of every rstest-bdd page.
BASE_PATH = "/rstest-bdd/"

# Every width is measured at this height, as the rendered-page checks in
# AGENTS.md set it.
HEIGHT = 900

# The chapter the storybook test chooses: the fifth, by zero-based index.
CHOSEN_CHAPTER = 4

# The narrowest width the site supports, a phone, and a desktop.
NARROWEST = 320
PHONE = 390
DESKTOP = 1440

# Every page the sub-site publishes, legal notices included.
PAGES = (
    "",
    "getting-started/",
    "guides/",
    "guides/feature-files/",
    "guides/steps/",
    "guides/fixtures-and-state/",
    "guides/binding-and-filtering/",
    "guides/async/",
    "guides/tooling/",
    "guides/migrate-to-0-6/",
    "harnesses/",
    "compare/",
    "roadmap/",
    "privacy-policy/",
    "terms-of-use/",
    "code-of-conduct/",
)

# The document's width against the viewport's, and the first few elements
# that reach past it, leaving out anything inside a region that scrolls on
# purpose.
LAYOUT = """JSON.stringify((() => {
  const viewport = document.documentElement.clientWidth;
  const offenders = [...document.querySelectorAll('body *')]
    .filter((el) => el.getBoundingClientRect().right > viewport + 1)
    .filter((el) => !el.closest('.rb-code-scroll, .rb-story__track'))
    .slice(0, 5)
    .map((el) => el.tagName + '.' + String(el.className).slice(0, 40));
  return {page: document.documentElement.scrollWidth, viewport, offenders};
})())"""

# The storybook's state after the chosen tab is clicked.
STORYBOOK = """JSON.stringify((() => {
  const tabs = [...document.querySelectorAll('[data-rb-chapter-tab]')];
  tabs[__CHOSEN__].click();
  const track = document.querySelector('[data-rb-storybook]');
  const chapter = document.querySelectorAll('[data-rb-chapter]')[__CHOSEN__];
  return {
    current: tabs.findIndex((tab) => tab.getAttribute('aria-current') === 'true'),
    counter: document.querySelector('[data-rb-story-count]').textContent,
    pagingHidden: document.querySelector('[data-rb-story-paging]').hidden,
    focused: document.activeElement === chapter,
    target: chapter.offsetLeft - track.querySelector('[data-rb-chapter]').offsetLeft,
  };
})())"""


def _open(drive: cabc.Callable[..., str], served: str, page: str, width: int) -> None:
    """Size the viewport, then load one rstest-bdd page into it.

    The order matters: a page loaded before the resize lays out at the old
    width, and the media queries would report the wrong layout.
    """
    drive("set", "viewport", str(width), str(HEIGHT))
    drive("open", f"{served}{BASE_PATH}{page}")


@pytest.mark.timeout(900)
@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("page", [pytest.param(p, id=p or "home") for p in PAGES])
def test_a_page_meets_wcag_aa(
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
def test_a_page_fits_the_narrowest_phone(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """At 320px nothing but a code region or the storybook scrolls sideways."""
    _open(drive, served, page, NARROWEST)
    layout = _evaluate(drive, LAYOUT)
    assert layout["page"] <= layout["viewport"], (
        f"{BASE_PATH}{page} lays out {layout['page']}px wide in a "
        f"{layout['viewport']}px viewport"
    )
    assert not layout["offenders"], (
        f"{BASE_PATH}{page} has elements past the viewport: {layout['offenders']}"
    )


@pytest.mark.timeout(900)
def test_a_chapter_tab_scrolls_the_storybook_to_its_chapter(
    drive: cabc.Callable[..., str], served: str
) -> None:
    """Choosing a tab marks it, names the chapter, and hands it focus."""
    _open(drive, served, "", DESKTOP)
    state = _evaluate(drive, STORYBOOK.replace("__CHOSEN__", str(CHOSEN_CHAPTER)))
    assert state["current"] == CHOSEN_CHAPTER, (
        f"the fifth tab should be current: {state}"
    )
    assert state["counter"] == f"Chapter {CHOSEN_CHAPTER + 1:02d} of 08", state
    assert not state["pagingHidden"], "the script should reveal the paging"
    assert state["focused"], "focus should move to the chosen chapter"
    assert state["target"] > 0, "the fifth chapter should sit along the strip"
