"""What the published Weaver pages actually do in a browser.

Everything else asserted about this sub-site is asserted against text. The
build tests read the delivered markup and the compiled stylesheet as strings;
the snapshot tests exercise the harness that drives a browser without ever
starting one. That leaves the questions a string cannot answer, and they are
the ones the migration turns on: whether a declared stylesheet is *served*,
whether the fonts and textures resolve, what a colour composites to once the
cascade and a translucent panel have had their say, and whether the sidebar
gives way to the drawer at a narrow viewport.

So these tests serve ``public/`` and drive a real Chromium over it via
``agent-browser``, which the snapshot harness already depends on. Requests are
read back from the browser rather than inferred from the markup, so a
stylesheet that 404s or an image fetched from somewhere else is observed
rather than argued about. Accessibility is checked with axe, which composites
colours the way a browser does and therefore measures contrast rather than
guessing at it — that is how the two defects fixed alongside this file were
found.

Both a narrow and a wide viewport are exercised, because the two layouts share
almost no chrome: at 360 the sidebar is off-canvas behind a toggle, and at
1440 it is the layout.

These are slower than the rest of the suite — a browser start, then a page
load per case. They are marked ``playwright`` so they can be deselected while
iterating on something else.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import subprocess
import typing as typ
from pathlib import Path

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc

REPO_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.playwright

# Four pages that between them carry every kind of chrome the sub-site has:
# the home page's hero, a page of prose panels, a command page's scrollable
# code blocks, and the figure-heavy explainer.
PAGES = ("", "safety/", "commands/act/", "how-it-works/")

# 360 is the narrowest viewport the design targets and the one that puts the
# sidebar off-canvas; 1440 is the width it was drawn against.
VIEWPORTS = (("mobile", 360, 800), ("desktop", 1440, 900))

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


def _free_port() -> int:
    """Ask the kernel for a port nothing is listening on.

    Returns
    -------
    int
        A port that was free a moment ago. The server's own bind probe and
        startup lock handle the gap between then and now.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(scope="session")
def served(built_site: Path) -> cabc.Iterator[str]:
    """Serve the published tree and yield its origin.

    Parameters
    ----------
    built_site
        The Weaver root, which the session fixture has just built.

    Yields
    ------
    str
        The origin the tree is being served on, without a trailing slash.
    """
    spec = importlib.util.spec_from_file_location(
        "weaver_snapshot", REPO_ROOT / "scripts" / "weaver_snapshot.py"
    )
    assert spec is not None, "scripts/weaver_snapshot.py could not be located"
    assert spec.loader is not None, "the spec for weaver_snapshot has no loader"
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)

    if not harness.HTTP_SERVER.is_file():  # pragma: no cover - environment guard
        pytest.skip(f"{harness.HTTP_SERVER} is missing; run 'bun install'")

    assert built_site.is_dir(), f"expected the built sub-site at {built_site}"
    with harness._served(_free_port()) as base:
        yield base


@pytest.fixture(scope="session")
def drive() -> cabc.Iterator[cabc.Callable[..., str]]:
    """Yield a way to run ``agent-browser`` in a session of this test run's own.

    ``agent-browser`` sessions are named globally and hold one viewport and one
    current page between calls, so a shared name would let a concurrent run
    resize the viewport out from under a page these tests had just opened.

    Yields
    ------
    callable
        Takes the subcommand and its arguments; returns stdout.
    """
    # `or pytest.skip(...)` rather than an `if`, because the skip's `NoReturn`
    # is what narrows this to `str` for the closure below.
    browser = shutil.which("agent-browser") or pytest.skip(
        "agent-browser is not on PATH"
    )

    session = ["--session", f"weaver-tests-{os.getpid()}"]

    def run(*args: str) -> str:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [browser, *args, *session],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=TOOL_TIMEOUT_SECONDS,
        )
        return completed.stdout

    try:
        yield run
    finally:
        # A session left open strands a browser daemon holding the viewport it
        # was last set to.
        subprocess.run(  # noqa: S603 - fixed argv, no shell
            [browser, "close", *session],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
            timeout=TOOL_TIMEOUT_SECONDS,
        )


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


def _accepted(page: str, rule: str, node: dict[str, typ.Any]) -> bool:
    """Say whether one axe failure is a recorded exception for this page."""
    target = " ".join(str(part) for part in node["target"])
    return any(
        page == accepted_page and rule == accepted_rule and marker in target
        for accepted_page, accepted_rule, marker in ACCEPTED
    )


CASES = [
    pytest.param(page, width, height, id=f"{name}-{page or 'home'}")
    for page in PAGES
    for name, width, height in VIEWPORTS
]


@pytest.mark.timeout(600)
@pytest.mark.parametrize(("page", "width", "height"), CASES)
def test_a_weaver_page_fetches_everything_from_the_local_server(
    drive: cabc.Callable[..., str], served: str, page: str, width: int, height: int
) -> None:
    """Self-containment is the migration's point, asserted from the browser.

    The static check on the delivered markup cannot see a URL a stylesheet
    builds, an image a script inserts, or a font a ``@font-face`` resolves. It
    also cannot see a request that failed. This reads the browser's own log,
    so all three are observed.
    """
    _open(drive, served, page, width, height)
    requests = _requests(drive)

    assert requests, "the browser reported no requests at all, not even the page"

    remote = sorted(
        {
            request["url"]
            for request in requests
            if not request["url"].startswith((served, "data:", "about:"))
        }
    )
    assert not remote, (
        f"/weaver/{page} at {width}px fetched from another origin: {remote}"
    )

    failed = sorted(
        {
            f"{request['status']} {request['url'].removeprefix(served)}"
            for request in requests
            if request.get("status", 0) >= 400  # noqa: PLR2004 - the HTTP error range
        }
    )
    assert not failed, (
        f"/weaver/{page} at {width}px has subresources that failed: {failed}"
    )


@pytest.mark.timeout(600)
@pytest.mark.parametrize(("page", "width", "height"), CASES)
def test_a_weaver_page_serves_its_own_stylesheet_fonts_and_script(
    drive: cabc.Callable[..., str], served: str, page: str, width: int, height: int
) -> None:
    """A page that fetched nothing at all would pass the check above vacuously.

    The sub-site used to pull Tailwind, Font Awesome, and its webfonts from
    three CDNs. Each now has to be served from the published tree, which means
    the browser has to have asked us for it.
    """
    _open(drive, served, page, width, height)
    kinds = {request["resourceType"] for request in _requests(drive)}

    assert {"Document", "Stylesheet", "Font", "Script"} <= kinds, (
        f"/weaver/{page} at {width}px fetched only {sorted(kinds)}; the compiled "
        "stylesheet, the webfonts and the drawer script should all come from here"
    )


@pytest.mark.timeout(900)
@pytest.mark.parametrize(("page", "width", "height"), CASES)
def test_a_weaver_page_meets_wcag_aa(
    drive: cabc.Callable[..., str], served: str, page: str, width: int, height: int
) -> None:
    """Contrast is a property of the rendered page, not of the class names.

    ``text-base-content`` says nothing about what it composites to through an
    ``opacity-60`` on a cream panel; only a browser can say, and what it said
    was 3.33:1. This check is what found that, and the four scrollable code
    panels no keyboard could reach.
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
    _open(drive, served, "safety/", 1440, 900)

    fired = {
        (violation["id"], marker)
        for violation in _violations(drive)
        for node in violation["nodes"]
        for marker in ("text-status-ok", "text-status-error")
        if marker in " ".join(str(part) for part in node["target"])
    }
    expected = {(rule, marker) for _page, rule, marker in ACCEPTED}

    assert fired == expected, (
        "the accepted contrast exceptions for pages/safety.jinja no longer "
        f"match what the page does. Expected {sorted(expected)}, observed "
        f"{sorted(fired)}. If they now pass, drop them from ACCEPTED and from "
        "the decision log."
    )


@pytest.mark.timeout(600)
@pytest.mark.parametrize("page", PAGES)
def test_exactly_one_nav_link_is_marked_as_the_current_page(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """`nav_link` compares each href against one current href, so one can win.

    Two would mean the companion macro handed down the wrong value; none would
    mean it handed down nothing, which is what an empty string does and what
    the macro returns for a page outside the nav. All four of these are in it.
    """
    _open(drive, served, page, 1440, 900)
    current = _evaluate(
        drive,
        "JSON.stringify([...document.querySelectorAll('[aria-current=\"page\"]')]"
        ".map((a) => a.getAttribute('href')))",
    )

    assert len(current) == 1, (
        f"/weaver/{page} marks {current} as current; exactly one nav link should be"
    )


@pytest.mark.timeout(600)
@pytest.mark.parametrize("page", PAGES)
def test_every_icon_renders_its_artwork(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """The icons are inlined from a generated macro, so a miss is a bare label.

    An unmapped name renders the literal text ``UNKNOWN ICON``, and a macro
    that generated an empty body would render an ``<svg>`` with nothing in it.
    Neither shows up in a stylesheet diff and neither is visible in the markup
    at a glance.
    """
    _open(drive, served, page, 1440, 900)
    report = _evaluate(
        drive,
        "JSON.stringify({"
        "empty: [...document.querySelectorAll('svg')]"
        ".filter((s) => s.children.length === 0).length,"
        "total: document.querySelectorAll('svg').length,"
        "unknown: document.body.textContent.includes('UNKNOWN ICON')})",
    )

    assert report["total"] > 0, f"/weaver/{page} rendered no icons at all"
    assert report["empty"] == 0, (
        f"/weaver/{page} has {report['empty']} icons with no artwork in them"
    )
    assert not report["unknown"], (
        f"/weaver/{page} names an icon the generated macro does not define"
    )


@pytest.mark.timeout(600)
@pytest.mark.parametrize("page", PAGES)
def test_the_sidebar_gives_way_to_a_drawer_at_a_narrow_viewport(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """The two layouts share no chrome, so each has to be checked at its width.

    At 1440 the sidebar is the navigation and there is no toggle to press. At
    360 the toggle is the navigation and the sidebar is off-canvas. Getting
    this backwards leaves a page with no way to navigate at all, on one width
    or the other.
    """
    measure = (
        "JSON.stringify((() => {"
        # The drawer toggle has no markup: `mobile-nav.js` builds it and
        # gives it this id, so its presence also proves the script ran.
        "const toggle = document.querySelector('#mobile-nav-toggle');"
        "const link = document.querySelector('.weaver-nav-link');"
        "const box = link ? link.getBoundingClientRect() : null;"
        "return {toggle: toggle ? toggle.getBoundingClientRect().width > 0 : false,"
        "sidebar: box ? box.width > 0 && box.right > 0 : false};"
        "})())"
    )

    _open(drive, served, page, 1440, 900)
    wide = _evaluate(drive, measure)
    _open(drive, served, page, 360, 800)
    narrow = _evaluate(drive, measure)

    assert wide["sidebar"], f"/weaver/{page} has no sidebar navigation at 1440px"
    assert not narrow["sidebar"], (
        f"/weaver/{page} still lays out the sidebar at 360px, where it does not fit"
    )
    assert narrow["toggle"], (
        f"/weaver/{page} has no drawer toggle at 360px, so the sidebar it hides "
        "cannot be opened"
    )


@pytest.mark.timeout(600)
@pytest.mark.parametrize("page", PAGES)
def test_no_page_scrolls_sideways_on_a_phone(
    drive: cabc.Callable[..., str], served: str, page: str
) -> None:
    """A page wider than the viewport is the classic mobile-layout failure.

    The code panels scroll on purpose and are allowed to; the document is not.
    A stray fixed width or an unwrapped heading pushes the whole page over, and
    every line of body text then needs a horizontal scroll to read.
    """
    _open(drive, served, page, 360, 800)
    overflow = _evaluate(
        drive,
        "JSON.stringify({page: document.documentElement.scrollWidth,"
        "viewport: window.innerWidth})",
    )

    assert overflow["page"] <= overflow["viewport"], (
        f"/weaver/{page} lays out {overflow['page']}px wide in a "
        f"{overflow['viewport']}px viewport, so the whole page scrolls sideways"
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
            "--port",
            str(_free_port()),
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
