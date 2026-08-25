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
import re
import shutil
import socket
import subprocess
import typing as typ
from pathlib import Path

import pytest
from ruamel.yaml import YAML

if typ.TYPE_CHECKING:
    import collections.abc as cabc

REPO_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.playwright


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
    weaver = YAML(typ="safe").load(
        (REPO_ROOT / "config" / "pages.yaml").read_text(encoding="utf-8")
    )["sites"]["weaver"]
    slugs = [page["output_slug"] for page in weaver["content_pages"]]
    slugs.extend(weaver["shared_content"])
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
    weaver = YAML(typ="safe").load(
        (REPO_ROOT / "config" / "pages.yaml").read_text(encoding="utf-8")
    )["sites"]["weaver"]
    return frozenset(f"{name}/" for name in weaver["shared_content"])


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


CASES = [
    pytest.param(page, width, height, id=f"{name}-{page or 'home'}")
    for page in PAGES
    for name, width, height in VIEWPORTS
]


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
