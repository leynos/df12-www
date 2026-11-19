"""Browser checks for the published wireframe sub-site.

Contrast and overflow are properties of the rendered page rather than of the
markup, so these tests read them back from ``agent-browser`` against the
built ``public/`` tree. They use the shared ``served`` and ``drive``
fixtures, so the suite relies on the site build the ``built_site`` fixture
runs.

The accessibility bar is the one AGENTS.md sets: zero axe violations against
WCAG 2.0 A and AA, at a phone width and a desktop width. Both are checked
because a code region only reports as an unreachable scroller once it
actually scrolls, and because the plates' controls wrap differently at each.
The sub-site carries no waivers, so any failure is a failure.

The plate tests drive the vendored Three.js runtime itself, in the headless
browser's software WebGL: under ordinary motion the hero plays with no Play
gate, and under reduced motion every plate is a poster until one is played,
which the runtime only honours through the site's local `allow-motion` patch.
"""

from __future__ import annotations

import time
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
    "scope/",
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


# Each plate's figure: its id, its live element's reported state, and its
# controls' visibility, for the playback tests to wait on.
PLATES = """JSON.stringify([...document.querySelectorAll('[data-wf-plate]')]
  .map((f) => {
  const live = f.querySelector('wireframe-plate');
  return {
    id: f.dataset.wfPlate,
    live: live ? live.dataset.state || 'mounting' : null,
    motion: live ? live.hasAttribute('allow-motion') : false,
    play: !f.querySelector('[data-wf-plate-play]').hidden,
    still: !f.querySelector('[data-wf-plate-still]').hidden,
    hidden: f.querySelector('[data-wf-plate-controls]').hidden,
  };
}))"""

# Press the hero plate's playback button, as a visitor would.
HERO_PLAY = (
    "document.querySelector('[data-wf-plate=\"27\"] [data-wf-plate-play]').click()"
)

# A plate the renderer is drawing and animating.
PLAYING = ("scanning", "stable")


def _plates(drive: cabc.Callable[..., str]) -> dict[str, dict[str, typ.Any]]:
    """Read every plate's state from the current page, keyed by plate id."""
    return {plate["id"]: plate for plate in _evaluate(drive, PLATES)}


def _await_plate(
    drive: cabc.Callable[..., str], plate: str, states: tuple[str, ...]
) -> dict[str, typ.Any]:
    """Wait up to 20 seconds for a plate's live element to report a state."""
    deadline = time.monotonic() + 20
    while True:
        current = _plates(drive)[plate]
        if current["live"] in states or time.monotonic() > deadline:
            return current
        drive("wait", "250")


@pytest.mark.timeout(300)
def test_the_hero_plate_plays_without_a_play_gate(
    drive: cabc.Callable[..., str], served: str
) -> None:
    """Under ordinary motion, Plate 27 starts on load, with no controls."""
    _open(drive, served, "", DESKTOP)
    hero = _await_plate(drive, "27", PLAYING)
    assert hero["live"] in PLAYING, f"the hero never started: {hero}"
    assert hero["hidden"], "ordinary motion shows no playback controls"
    assert not hero["motion"], "ordinary motion needs no opt-in"
    below = _plates(drive)["15"]
    assert below["live"] is None, "a plate far below the fold rendered early"


@pytest.mark.timeout(300)
def test_reduced_motion_is_posters_until_one_is_played(
    drive: cabc.Callable[..., str], served: str
) -> None:
    """Under reduced motion, nothing renders until Play, then only that plate."""
    drive("set", "media", "dark", "reduced-motion")
    try:
        _open(drive, served, "", DESKTOP)
        drive("wait", "1000")
        plates = _plates(drive)
        assert all(plate["live"] is None for plate in plates.values()), plates
        assert all(plate["play"] for plate in plates.values()), plates
        drive("eval", HERO_PLAY)
        hero = _await_plate(drive, "27", PLAYING)
        assert hero["live"] in PLAYING, f"Play did not animate the plate: {hero}"
        assert hero["motion"], "the opt-in is not recorded on the element"
        assert not hero["play"]
        assert hero["still"], "an opted-in plate offers Show still"
        others = {id_: plate for id_, plate in _plates(drive).items() if id_ != "27"}
        assert all(plate["live"] is None for plate in others.values()), others
    finally:
        drive("set", "media", "dark")
