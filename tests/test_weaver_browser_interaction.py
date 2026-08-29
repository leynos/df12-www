"""What the Weaver pages do when something interacts with them.

The copy controls are inline `onclick` handlers, so nothing between the markup
and a real click exercises them. The code panels are meant to scroll rather
than wrap, and the guarantee worth pinning is that a long line scrolls its
panel and not the document. The drawer is a UI flow that the fake DOM cannot
speak for, and its telemetry seam only exists once the page has loaded the
script and the markup that calls it. And `capture` is a command an operator
types, exercised here end to end rather than through its seams.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import typing as typ
from pathlib import Path

import pytest

from tests.support.weaver_browser import (
    DESKTOP_HEIGHT,
    DESKTOP_WIDTH,
    MOBILE_HEIGHT,
    MOBILE_WIDTH,
    _evaluate,
    _open,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

REPO_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.playwright


# Pages carrying a copy-to-clipboard control, and what each one should hand
# over. Every Weaver copy button is an inline `onclick`, because no Weaver page
# loads a copy-button script; the Netsuke suite tests a different mechanism
# entirely, so nothing covered these until now.
# What the drawer's state looks like from outside: the toggle's ARIA, whether
# the backdrop is displayed, where focus sits, and each axis of body scroll.
_DRAWER_STATE = (
    "JSON.stringify((() => {"
    "const toggle = document.getElementById('mobile-nav-toggle');"
    "if (!toggle) return {toggle: false};"
    "const backdrop = document.getElementById('mobile-nav-backdrop');"
    "const sidebar = document.getElementById('sidebar');"
    "const nav = sidebar ? sidebar.querySelector('nav') : null;"
    "const active = document.activeElement;"
    "const body = getComputedStyle(document.body);"
    "return {toggle: true, expanded: toggle.getAttribute('aria-expanded'),"
    " backdrop: backdrop ? getComputedStyle(backdrop).display : 'absent',"
    # The drawer is the nav inside the sidebar, not the sidebar itself:
    # `.has-mobile-nav #sidebar nav` hides it, and `#sidebar.mobile-nav-open
    # nav` is what brings it back — as a fixed overlay, so it covers the page
    # rather than pushing it down.
    " navDisplay: nav ? getComputedStyle(nav).display : 'absent',"
    " navPosition: nav ? getComputedStyle(nav).position : 'absent',"
    # A page without a sidebar, or with nothing focused, is a failure to
    # report rather than one to throw on: `contains` on null and `.tagName`
    # on null both abort the probe before it can say what it found.
    " focusInDrawer: Boolean(sidebar && active && sidebar.contains(active)),"
    " active: active ? active.tagName + '#' + (active.id || '') : 'none',"
    " bodyOverflowY: body.overflowY,"
    # The *inline* declarations as well as the computed ones. The body already
    # carries `overflow-x: hidden` from a class, so a script setting both axes
    # computes identically to one setting only the vertical; what it replaces
    # is the class's declaration, and only the inline style shows that.
    " inlineOverflowX: document.body.style.overflowX,"
    " inlineOverflowY: document.body.style.overflowY};"
    "})())"
)

COPY_CONTROLS = [
    ("", "cargo install weaver"),
    ("install/", None),
]


@pytest.mark.timeout(600)
@pytest.mark.parametrize(("page", "expected"), COPY_CONTROLS)
def test_a_copy_control_hands_the_clipboard_what_it_shows(
    drive: cabc.Callable[..., str], served: str, page: str, expected: str | None
) -> None:
    """A copy button that copies the wrong thing looks exactly like one that works.

    The handler is an `onclick` attribute in the template, so nothing between
    the markup and a real click exercises it — a typo in the string, or a
    quote that ends the attribute early, ships silently. `navigator.clipboard`
    is stubbed rather than read back, because a headless browser's clipboard
    permissions are their own source of flakiness and the question here is
    what the handler passed, not whether Chromium would store it.

    Where `expected` is None the assertion is that every control copies the
    text it sits beside, which is the invariant that holds for the three
    buttons on the install page.
    """
    _open(drive, served, page, DESKTOP_WIDTH, DESKTOP_HEIGHT)
    copied = _evaluate(
        drive,
        "JSON.stringify((() => {"
        "const copied = [];"
        "Object.defineProperty(navigator, 'clipboard', {configurable: true,"
        " value: {writeText: (text) => { copied.push(text);"
        " return Promise.resolve(); }}});"
        "const shown = [];"
        # The two pages label their controls differently — `title` on the home
        # page, visible text on the install page — so they are found by the
        # seam they share rather than by how they are labelled.
        "for (const button of document.querySelectorAll("
        "'button[onclick*=df12WeaverCopy]')) {"
        "  shown.push(button.closest('div').textContent.replace(/\\s+/g,' ').trim());"
        "  button.click();"
        "}"
        "return {copied, shown};"
        "})())",
    )

    assert copied["copied"], (
        f"/weaver/{page} has a copy control that handed the clipboard nothing; "
        "the handler did not run"
    )
    if expected is not None:
        assert copied["copied"] == [expected], (
            f"/weaver/{page}'s copy control passed {copied['copied']} rather "
            f"than {[expected]}"
        )
    # Equal lengths first: `zip` would otherwise stop at the shorter list, so
    # a control that never reached `writeText` would leave its pair unchecked
    # rather than failing.
    assert len(copied["copied"]) == len(copied["shown"]), (
        f"/weaver/{page} has {len(copied['shown'])} copy controls but only "
        f"{len(copied['copied'])} reached the clipboard: {copied}"
    )
    for text, beside in zip(copied["copied"], copied["shown"], strict=True):
        assert text in beside, (
            f"/weaver/{page} copies {text!r} from a control sitting beside "
            f"{beside!r}, so the button copies something other than what it shows"
        )


@pytest.mark.timeout(600)
@pytest.mark.parametrize("page", ["docs/", "commands/act/", "sempai/"])
def test_a_long_code_line_scrolls_its_panel_and_not_the_page(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """Code panels scroll on purpose; the document must not scroll with them.

    The mobile rule lets code break mid-token, but a `pre` inherits
    ``white-space: pre`` unless a utility says otherwise, and `overflow-wrap`
    does nothing to a line that is not allowed to wrap at all. Those panels
    are meant to scroll, and they are reachable from a keyboard so that they
    can be. What must not happen is the document scrolling instead, which is
    what puts every line of body text out of reach.

    A three-hundred-character line is injected rather than waited for, so the
    guarantee is tested rather than the current content, and the panel is made
    to scroll rather than assumed able to: `overflow-x: hidden` reports a
    `scrollWidth` past its `clientWidth` exactly as `auto` does, while
    offering no way to reach what it clips.
    """
    _open(drive, served, page, MOBILE_WIDTH, MOBILE_HEIGHT)
    result = _evaluate(
        drive,
        "JSON.stringify((() => {"
        "const pre = document.querySelector('pre');"
        "if (!pre) return {found: false};"
        "pre.textContent = 'weaver observe get-definition --overrides '"
        " + 'x'.repeat(300);"
        # Walk out from the `pre` looking for an ancestor that *does* scroll,
        # rather than one that merely has a non-visible `overflow-x`. Both
        # `hidden` and `clip` satisfy "not visible" and both report a
        # `scrollWidth` past their `clientWidth` while clipping the line away
        # with no way to reach it, so neither the computed value nor the
        # measurement is sufficient on its own. Asking the element to scroll
        # and seeing whether it moves is.
        "const overflows = [];"
        "let scroller = pre;"
        "let scrolls = false;"
        "while (scroller) {"
        "  const overflowX = getComputedStyle(scroller).overflowX;"
        "  overflows.push(overflowX);"
        "  if (overflowX === 'auto' || overflowX === 'scroll') {"
        "    const start = scroller.scrollLeft;"
        "    scroller.scrollLeft = scroller.scrollWidth;"
        "    if (scroller.scrollLeft > start) { scrolls = true; }"
        "    scroller.scrollLeft = start;"
        "    if (scrolls) break;"
        "  }"
        "  scroller = scroller.parentElement;"
        "}"
        "return {found: true, page: document.documentElement.scrollWidth,"
        " viewport: window.innerWidth,"
        " wrapped: pre.scrollWidth <= pre.clientWidth + 1,"
        " scrollable: scrolls, overflows: overflows.slice(0, 6)};"
        "})())",
    )

    assert result["found"], f"/weaver/{page} has no code panel to test"
    assert result["page"] <= result["viewport"], (
        f"a long line in a code panel on /weaver/{page} pushed the document to "
        f"{result['page']}px in a {result['viewport']}px viewport"
    )
    # A panel may answer a long line either way: by wrapping it, where the
    # markup asks for `whitespace-pre-wrap`, or by scrolling it, which is the
    # default and why these panels are keyboard-reachable. What it may not do
    # is clip the line away with no means of reading it — which is why
    # `scrollable` above is the result of actually scrolling something, not of
    # inferring that something could be scrolled.
    assert result["wrapped"] or result["scrollable"], (
        f"/weaver/{page}'s code panel neither wrapped the long line nor "
        f"scrolled when asked to, so the end of it cannot be read. The "
        f"overflow-x values out from the panel were {result['overflows']}"
    )


@pytest.mark.timeout(900)
def test_the_capture_command_writes_one_snapshot_per_page(
    built_site: Path, tmp_path: Path
) -> None:
    """The snapshot harness's parts are tested; this runs the command itself.

    Everything between ``capture``'s argument parsing and the JSON on disk —
    the page enumeration, the server, the browser, the slugs — is exercised
    here as one, through the same command line an operator would type.
    """
    uv_exe = shutil.which("uv") or pytest.skip("uv is not on PATH")
    if not shutil.which("bun"):  # pragma: no cover - environment guard
        pytest.skip("bun is not on PATH")

    out_dir = tmp_path / "snapshots"
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [
            uv_exe,
            "run",
            "python",
            "scripts/weaver_snapshot.py",
            "capture",
            str(out_dir),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    assert completed.returncode == 0, (
        f"capture exited {completed.returncode}: {completed.stderr[-2000:]}"
    )

    pages = sorted(path.parent for path in built_site.rglob("index.html"))
    written = sorted(out_dir.glob("*.json"))
    assert len(written) == len(pages), (
        f"expected one snapshot per page ({len(pages)}), got "
        f"{[path.name for path in written]}"
    )

    # A snapshot that parses but holds no tree would pass a file count and
    # fail every later comparison for a reason nobody could see.
    for snapshot in written:
        payload = json.loads(snapshot.read_text(encoding="utf-8"))
        assert payload["payload"]["tree"]["children"], (
            f"{snapshot.name} carries no rendered tree"
        )


@pytest.mark.timeout(600)
@pytest.mark.parametrize("page", ["privacy-policy/", ""])
def test_the_drawer_opens_on_a_published_page(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """The drawer is a UI flow, and the fake DOM cannot say it works in a browser.

    `tests/js/weaver-mobile-nav.test.mjs` drives this logic against happy-dom,
    which is the right place for the focus bookkeeping — but it supplies its
    own markup and its own stylesheet-free window. It cannot say whether the
    published page carries the elements the script looks for, nor whether the
    compiled CSS actually shows the backdrop when the class lands.

    `privacy-policy/` is the case worth pinning: it is shared content, rendered
    through `shared_content_page.jinja` rather than a Weaver template of its
    own, and it was the sub-site's legal pages that lacked mobile navigation
    before this migration.
    """
    _open(drive, served, page, MOBILE_WIDTH, MOBILE_HEIGHT)
    before = _evaluate(drive, _DRAWER_STATE)

    assert before["toggle"], f"/weaver/{page} has no drawer toggle at 360px"
    assert before["expanded"] == "false", (
        f"the drawer should start closed; aria-expanded was {before['expanded']!r}"
    )
    assert before["backdrop"] == "none", (
        f"the backdrop should be hidden while closed; got {before['backdrop']!r}"
    )
    assert before["navDisplay"] == "none", (
        "the navigation should be hidden while the drawer is closed; got "
        f"{before['navDisplay']!r}"
    )

    drive("eval", "document.getElementById('mobile-nav-toggle').click()")
    after = _evaluate(drive, _DRAWER_STATE)

    assert after["expanded"] == "true", (
        f"opening should set aria-expanded; got {after['expanded']!r}"
    )
    assert after["backdrop"] != "none", (
        "the backdrop should be shown, or the drawer does not read as modal; "
        f"display was {after['backdrop']!r}"
    )
    # The two declarations `#sidebar.mobile-nav-open nav` exists to make. A
    # selector that stopped matching would leave the toggle flipping ARIA and
    # the backdrop appearing over a navigation still set to `display: none`,
    # which reads as a drawer that opens onto nothing.
    assert after["navDisplay"] not in ("none", "absent"), (
        "opening the drawer should render the navigation; its display was "
        f"{after['navDisplay']!r}, so the drawer opens onto nothing"
    )
    assert after["navPosition"] == "fixed", (
        "the drawer should overlay the page rather than push it down; the "
        f"navigation's position was {after['navPosition']!r}"
    )
    assert after["focusInDrawer"], (
        "focus should enter the drawer, or a keyboard user tabs through the "
        f"page behind it; the active element was {after['active']}"
    )
    assert after["bodyOverflowY"] == "hidden", (
        f"the page behind the drawer should not scroll; got {after['bodyOverflowY']!r}"
    )
    # Only the vertical axis. `style.overflow` would set both inline,
    # replacing the `overflow-x: hidden` the body carries as a class for as
    # long as the drawer is open, and letting the page jump sideways.
    assert after["inlineOverflowY"] == "hidden", (
        f"the lock should be an inline overflow-y; got {after['inlineOverflowY']!r}"
    )
    assert after["inlineOverflowX"] == "", (
        f"opening the drawer set the horizontal axis inline too, to "
        f"{after['inlineOverflowX']!r}, displacing the class that clips it"
    )


@pytest.mark.timeout(600)
def test_a_copy_control_reports_its_outcome_and_not_its_contents(
    drive: cabc.Callable[..., str], served: str
) -> None:
    """The copy controls are inline handlers, so the seam has to be real markup.

    A unit test can prove `df12WeaverCopy` emits the right event; only a page
    can prove the buttons actually call it, and that `telemetry.js` is served
    and loaded before they are pressed. What the event may contain is asserted
    here too, against the copied text itself: the string the button copies is
    distinctive, so if any field carried it this would say so.
    """
    _open(drive, served, "install/", DESKTOP_WIDTH, DESKTOP_HEIGHT)
    seen = _evaluate(
        drive,
        # Returned as a promise rather than a JSON string: `agent-browser`
        # awaits one and reports the resolved value, whereas `JSON.stringify`
        # of a pending promise is `{}`.
        "(() => {"
        "const events = [];"
        "globalThis.df12WeaverNavTelemetry = (event) => events.push(event);"
        "const copied = [];"
        "Object.defineProperty(navigator, 'clipboard', {configurable: true,"
        " value: {writeText: (text) => { copied.push(text);"
        " return Promise.resolve(); }}});"
        "const button = document.querySelector('button[onclick*=df12WeaverCopy]');"
        "if (!button) return {seam: false};"
        "button.click();"
        "return new Promise((resolve) => setTimeout(() => resolve("
        " {seam: true, events, copied}), 0));"
        "})()",
    )

    assert seen["seam"], (
        "no copy control on /weaver/install/ routes through `df12WeaverCopy`, "
        "so the inline handlers have no telemetry seam at all"
    )
    assert seen["copied"], "the control copied nothing, so it did not run"
    assert seen["events"] == [
        {
            "component": "weaver-copy-button",
            "operation": "clipboard",
            "outcome": "copied",
        }
    ], f"expected one fixed-schema copy event; got {seen['events']}"

    # The copied text is distinctive, and nothing in the event may carry it —
    # nor anything else about this page.
    payload = json.dumps(seen["events"])
    for forbidden in (*seen["copied"], "install", "/weaver/", served):
        assert forbidden not in payload, (
            f"the telemetry event carried {forbidden!r}, which is page or "
            f"clipboard content: {payload}"
        )
