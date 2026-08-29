"""Tests for the Stilyagi focus indicator.

The sub-site draws one focus ring, declared once in ``colors-and-type.css``
and tuned per control only where an outward ring would be clipped. Two things
can quietly remove it, and both have happened:

* A ring coloured for a control's *fill* while being painted on the surface
  *around* it. The active RsDoc filter chip is the sharp case — an ink chip on
  a paper bar — and a paper ring at the shared outward offset vanished on it.
* A control gaining no ring at all.

:class:`TestFocusRingTokens` encodes the first as a rule about the stylesheets
themselves, so it runs in the ordinary gate without a browser.
:func:`test_active_namespace_chip_shows_a_keyboard_focus_ring` renders the real
docs page and measures the ring in Chromium.

Usage
-----
Run ``pytest tests/test_stilyagi_focus.py -v`` or ``make test``.

The browser test is marked ``playwright``. Playwright is not a dependency of
this repository, so the test skips unless it is installed alongside a Chromium
build::

    bun add -d playwright
    bun x playwright install chromium

``SKIP_PLAYWRIGHT=1 make test`` skips it outright. The three checks in
:class:`TestFocusRingTokens` need no browser and always run, and it is those
that would have caught the regression this module was written for.
"""

from __future__ import annotations

import functools
import http.server
import json
import os
import re
import shutil
import socketserver
import subprocess
import threading
import typing as typ
from contextlib import contextmanager
from pathlib import Path

import pytest

from df12_pages.config import ContentPageConfig
from df12_pages.content_page import ContentPageGenerator

if typ.TYPE_CHECKING:
    import collections.abc as cabc

REPO_ROOT = Path(__file__).resolve().parents[1]
STILYAGI_TEMPLATES = REPO_ROOT / "templates" / "stilyagi"
STILYAGI_STATIC = REPO_ROOT / "src" / "static" / "stilyagi"
STYLES = STILYAGI_STATIC / "assets" / "styles"
#: The compiled-stylesheet sources; the shared tokens and most page partials
#: live here since the daisyUI migration, while anything not yet migrated
#: stays under STYLES.
STYLE_SOURCES = REPO_ROOT / "src" / "styles" / "stilyagi"
COMPILED_STYLESHEET = (
    REPO_ROOT / "public" / "stilyagi" / "assets" / "styles" / "stilyagi.css"
)
FOCUS_PROBE = Path(__file__).parent / "support" / "stilyagi_focus_probe.mjs"

#: The namespace whose active chip is filled with ink, so its ring is the one
#: that disappears if it is coloured for the fill rather than for the bar.
INK_FILLED_NAMESPACE = "rsdoc"

#: WCAG 2.2 asks 3:1 of a non-text indicator against its adjacent colour.
NON_TEXT_CONTRAST_FLOOR = 3.0

#: A hairline ring reads as a border rather than a state; the shared treatment
#: is 3px, and anything under this would be a quiet weakening of it.
MIN_RING_WIDTH_PX = 2

#: The chip row is the wide-viewport control; a select replaces it at or below
#: this width, so the chip only exists to be focused above it. The probe runs
#: at 1440px.
CHIP_ROW_MIN_WIDTH = 1280

_RULE_RE = re.compile(r"(?P<selector>[^{}]+)\{(?P<body>[^{}]*)\}")
_PAPER_RING_RE = re.compile(r"--focus-ring-color\s*:\s*var\(\s*--(?:color-)?paper\s*\)")
_OUTLINE_OFFSET_RE = re.compile(r"outline-offset\s*:\s*(?P<value>-?[\d.]+)px")


def _stylesheets() -> cabc.Iterator[Path]:
    """Yield every hand-written Stilyagi stylesheet.

    ``syntax.css`` is generated from a Pygments style and carries no focus
    rules, so it is excluded rather than parsed.
    """
    for root in (STYLES, STYLE_SOURCES):
        for path in sorted(root.rglob("*.css")):
            if path.name != "syntax.css":
                yield path


class TestFocusRingTokens:
    """The paper ring is only ever used where it is painted on ink."""

    def test_every_paper_ring_is_drawn_inside_its_control(self) -> None:
        """A paper ring at an outward offset lands on the paper page.

        The ring's colour has to answer to the surface it is painted on, not
        the one inside the control. Re-pointing it to paper is therefore only
        correct alongside a negative ``outline-offset``, which is what puts the
        ring over the control's own ink ground.
        """
        offenders: list[str] = []
        for path in _stylesheets():
            for rule in _RULE_RE.finditer(path.read_text(encoding="utf-8")):
                body = rule.group("body")
                if not _PAPER_RING_RE.search(body):
                    continue
                offset = _OUTLINE_OFFSET_RE.search(body)
                if offset is None or float(offset.group("value")) >= 0:
                    selector = " ".join(rule.group("selector").split())
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {selector}")

        assert not offenders, (
            "these rules give a control a paper focus ring without also "
            "drawing it inside the control, so the ring is painted on the "
            "paper page and cannot be seen: " + "; ".join(offenders)
        )

    def test_the_shared_ring_is_ink_and_drawn_outside(self) -> None:
        """The default suits the common case: any control on a paper page."""
        tokens = (STYLE_SOURCES / "site-base.css").read_text(encoding="utf-8")
        assert "--focus-ring-color: var(--color-ink);" in tokens, (
            "the shared ring should default to ink, which holds against every "
            "paper surface the site has"
        )
        assert "--focus-ring-offset: 2px;" in tokens, (
            "the shared ring should sit outside the control, where the ground "
            "is the page rather than the control's own fill"
        )

    def test_the_chip_row_is_the_wide_viewport_control(self) -> None:
        """The chip only exists to be focused above the breakpoint.

        Below it the chips are hidden and a native select drives the filter, so
        a focus check on the chip is only meaningful at a wider viewport.
        """
        docs_css = (STYLES / "pages" / "docs.css").read_text(encoding="utf-8")
        assert f"@media (width <= {CHIP_ROW_MIN_WIDTH}px)" in docs_css
        assert ".filter-chip {\n    display: none;\n  }" in docs_css


@pytest.fixture(scope="module")
def served_docs_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Render the docs page into a tree whose asset paths resolve.

    The layout links its stylesheets and scripts from ``/stilyagi/assets/``, so
    the served root has to carry the real assets at that path; the page is
    styled by the same files the site ships.
    """
    root = tmp_path_factory.mktemp("stilyagi-site")
    shutil.copytree(STILYAGI_STATIC / "assets", root / "stilyagi" / "assets")

    # The layout links the compiled Tailwind + daisyUI sheet, which is build
    # output rather than a static asset; the tree serves the site's real
    # stylesheet or the page under test is unstyled.
    if not COMPILED_STYLESHEET.exists():
        pytest.skip("compiled Stilyagi stylesheet missing; run `bun run build:css`")
    shutil.copy(
        COMPILED_STYLESHEET, root / "stilyagi" / "assets" / "styles" / "stilyagi.css"
    )

    config = ContentPageConfig(
        key="docs",
        label="Docs",
        template="pages/docs.jinja",
        output_slug="docs",
    )
    generator = ContentPageGenerator(
        config,
        root / "stilyagi",
        templates_dir=STILYAGI_TEMPLATES,
        nav_links=[],
        stylesheet="assets/styles/stilyagi-site.css",
    )
    generator.run()
    return root


@contextmanager
def _http_serve(directory: Path) -> cabc.Iterator[int]:
    """Serve *directory* on a free port, yielding it.

    The layout links its assets from ``/stilyagi/assets/``, so the page has to
    be fetched over HTTP from a root that carries them rather than opened as a
    file.
    """

    class _SilentHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    handler = functools.partial(_SilentHandler, directory=str(directory))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield httpd.server_address[1]
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


def _installed_chromium() -> str | None:
    """Return an installed Chromium binary, newest revision first.

    Playwright launches the revision it was built against, which is not
    necessarily one of the revisions on disk: the package and the browsers are
    installed separately and drift apart. Handing it one that exists keeps the
    check runnable without a fresh download.
    """
    browsers = Path(
        os.environ.get(
            "PLAYWRIGHT_BROWSERS_PATH", Path.home() / ".cache" / "ms-playwright"
        )
    )
    candidates = sorted(
        (
            binary
            for pattern in ("chromium-*", "chromium_headless_shell-*")
            for build in browsers.glob(pattern)
            for name in ("chrome", "chrome-headless-shell", "headless_shell")
            for binary in build.glob(f"*/{name}")
            if binary.is_file()
        ),
        key=lambda path: path.parent.parent.name,
        reverse=True,
    )
    return str(candidates[0]) if candidates else None


def _skip_unless_browser_available() -> None:
    """Skip when the browser tooling this test drives is not installed."""
    if _installed_chromium() is None:  # pragma: no cover - environment guard
        pytest.skip(
            "no Playwright Chromium build found; run `bun x playwright install "
            "chromium`"
        )
    if shutil.which("bun") is None:  # pragma: no cover - environment guard
        pytest.skip("bun is required to drive the focus probe")


@pytest.mark.playwright
@pytest.mark.timeout(120)
def test_active_namespace_chip_shows_a_keyboard_focus_ring(
    served_docs_root: Path,
) -> None:
    """The active ink-filled chip keeps a ring the reader can actually see.

    Selecting RsDoc fills the chip with ink while its ring is still drawn on
    the paper filter bar around it. A ring coloured for the fill is invisible
    there, which is the regression this guards.
    """
    _skip_unless_browser_available()
    bun_exe = typ.cast("str", shutil.which("bun"))
    environment = os.environ | {
        "PLAYWRIGHT_CHROMIUM_EXECUTABLE": typ.cast("str", _installed_chromium())
    }

    with _http_serve(served_docs_root) as port:
        url = f"http://127.0.0.1:{port}/stilyagi/docs/"
        try:
            probe = subprocess.run(  # noqa: S603 - fixed argv, paths from fixtures
                [bun_exe, str(FOCUS_PROBE), url, INK_FILLED_NAMESPACE],
                cwd=REPO_ROOT,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
                timeout=90,
            )
        except subprocess.CalledProcessError as exc:  # pragma: no cover - guard
            missing = ("Cannot find package", "Cannot find module")
            if any(text in exc.stderr for text in missing):
                pytest.skip(
                    "the Playwright node package is not installed; run "
                    "`bun add -d playwright` to run this check locally"
                )
            raise
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - guard
            pytest.skip(f"focus probe timed out: {exc}")

    result = json.loads(probe.stdout)
    keyboard, pointer = result["keyboard"], result["pointer"]

    assert f"ns-{INK_FILLED_NAMESPACE}" in keyboard["classes"], (
        "selecting the namespace should tint the chip, which is what puts an "
        f"ink fill under the ring; got {keyboard['classes']!r}"
    )
    assert "active" in keyboard["classes"]
    assert keyboard["displayed"], "the chip row should be the control at 1440px"

    assert keyboard["outlineStyle"] != "none", (
        "the focused chip should draw a ring; it had none"
    )
    assert keyboard["outlineWidth"] >= MIN_RING_WIDTH_PX, (
        f"the ring should be substantial, got {keyboard['outlineWidth']}px"
    )
    assert keyboard["contrast"] >= NON_TEXT_CONTRAST_FLOOR, (
        "the ring should be visible against the surface it is painted on: "
        f"{keyboard['outlineColor']} on rgb{tuple(keyboard['ground'])} measures "
        f"{keyboard['contrast']}:1, under the {NON_TEXT_CONTRAST_FLOOR}:1 floor"
    )

    assert pointer["outlineStyle"] == "none", (
        "a pointer user should see no ring; :focus-visible is what keeps the "
        f"treatment to keyboard navigation, but the chip drew {pointer['outlineColor']}"
    )
