"""Shared pieces for the browser-driven Stilyagi suites.

The browser guard, the little HTTP server, and the colour arithmetic that
turns a computed style into a pass or a fail. ``test_stilyagi_focus.py``
and ``test_stilyagi_browser.py`` both drive a Playwright Chromium through
a bun probe script, and this module is the one definition of how that
tooling is found and how its answers are read.

Nothing here is Weaver's: the Weaver suites drive ``agent-browser`` over
the pages listed in ``config/pages.yaml`` and share none of this plumbing.
"""

from __future__ import annotations

import functools
import http.server
import os
import re
import shutil
import socketserver
import threading
import typing as typ
from contextlib import contextmanager
from pathlib import Path

import pytest

if typ.TYPE_CHECKING:
    import collections.abc as cabc

#: The width the design was drawn against, and the narrow width the
#: sub-site's popover navigation targets.
DESKTOP_VIEWPORT = (1440, 900)
MOBILE_VIEWPORT = (390, 844)

#: The Stilyagi palette, as the browser will report it. Each value is the
#: sRGB triple of a token declared in ``src/styles/stilyagi.css``; a browser
#: computes ``var(--color-paper)`` down to ``rgb(239, 228, 206)``, so the
#: contracts compare against these rather than against variable names.
PAPER = (239, 228, 206)
PAPER_SHADE = (228, 215, 185)
INK = (15, 15, 15)
INK_SOFT = (42, 42, 42)
PRESS_RED = (194, 39, 46)
PRESS_RED_TEXT = (164, 33, 39)
PRESS_RED_ON_INK = (218, 71, 78)
SIGNAL_SAGE_SOLID = (100, 105, 64)
JAZZ_OCHRE = (214, 159, 46)

#: Channel counts a computed colour may carry, and the sRGB transfer
#: function's linear-segment threshold.
_RGB_PARTS = 3
_RGBA_PARTS = 4
_SRGB_LINEAR_THRESHOLD = 0.04045

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_PX_VALUE = re.compile(r"^(-?\d+(?:\.\d+)?)px$")
_URL_VALUE = re.compile(r"url\([^)]*\)")


def installed_chromium() -> str | None:
    """Return an installed Playwright Chromium binary, newest revision first.

    Playwright launches the revision it was built against, which is not
    necessarily one of the revisions on disk: the package and the browsers
    are installed separately and drift apart. Handing it one that exists
    keeps the checks runnable without a fresh download.
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


def skip_unless_browser_available() -> None:
    """Skip when the browser tooling these tests drive is not installed."""
    if installed_chromium() is None:  # pragma: no cover - environment guard
        pytest.skip(
            "no Playwright Chromium build found; run `bun x playwright install "
            "chromium`"
        )
    if shutil.which("bun") is None:  # pragma: no cover - environment guard
        pytest.skip("bun is required to drive the browser probes")


@contextmanager
def http_serve(directory: Path) -> cabc.Iterator[int]:
    """Serve *directory* on a free port, yielding the port.

    The layouts link their assets from absolute paths such as
    ``/stilyagi/assets/``, so a page has to be fetched over HTTP from a root
    that carries them rather than opened as a file.
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


def parse_css_color(value: str) -> tuple[float, float, float, float]:
    """Read a computed CSS colour into ``(r, g, b, alpha)`` on 0-255 / 0-1.

    Chromium reports computed colours as ``rgb(...)``, ``rgba(...)``, or —
    for wide-gamut declarations — ``color(srgb ...)`` with 0-1 channels.
    All three arrive here; anything else is a malformed answer worth failing
    loudly on.
    """
    numbers = [float(part) for part in _NUMBER.findall(value)]
    if len(numbers) not in (_RGB_PARTS, _RGBA_PARTS):
        message = f"cannot read {value!r} as a CSS colour"
        raise ValueError(message)
    alpha = numbers[3] if len(numbers) == _RGBA_PARTS else 1.0
    if value.startswith("color("):
        return (numbers[0] * 255, numbers[1] * 255, numbers[2] * 255, alpha)
    return (numbers[0], numbers[1], numbers[2], alpha)


def relative_luminance(rgb: cabc.Sequence[float]) -> float:
    """Return the WCAG relative luminance of an sRGB triple on 0-255."""

    def channel(component: float) -> float:
        scaled = component / 255
        if scaled <= _SRGB_LINEAR_THRESHOLD:
            return scaled / 12.92
        return ((scaled + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2])
    )


def contrast_ratio(a: cabc.Sequence[float], b: cabc.Sequence[float]) -> float:
    """Return the WCAG contrast ratio between two sRGB triples on 0-255."""
    lighter, darker = sorted(
        (relative_luminance(a), relative_luminance(b)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


def normalize_style(style: cabc.Mapping[str, object]) -> dict[str, object]:
    """Make one probed style dictionary stable enough to snapshot.

    Pixel lengths are rounded to one decimal so sub-pixel layout noise does
    not churn the snapshot, and any ``url(...)`` is masked because it names
    the throwaway origin the test served the page from. Keys come back
    sorted so the serialization is deterministic.
    """
    normalized: dict[str, object] = {}
    for key in sorted(style):
        value = style[key]
        if isinstance(value, float):
            value = round(value, 1)
        elif isinstance(value, str):
            match = _PX_VALUE.match(value)
            if match:
                value = f"{round(float(match.group(1)), 1)}px"
            else:
                value = _URL_VALUE.sub("url([redacted])", value)
        normalized[key] = value
    return normalized


def class_tokens(class_attr: str) -> frozenset[str]:
    """Return the whole class tokens in a ``className`` string."""
    return frozenset(class_attr.split())
