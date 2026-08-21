"""Capture and compare computed-style snapshots of the Weaver sub-site.

The Weaver sub-site is being migrated from the Tailwind Play CDN to the
repository's compiled Tailwind v4 and daisyUI v5 pipeline. The migration is
meant to be behaviour-preserving, so each step is judged by diffing a fresh
snapshot against a baseline taken before any edit. See
``docs/execplans/weaver-daisy-migration.md``.

Three subcommands, each safe to re-run:

    uv run python scripts/weaver_snapshot.py capture .weaver-baseline
    uv run python scripts/weaver_snapshot.py shots .weaver-baseline-shots
    uv run python scripts/weaver_snapshot.py diff .weaver-baseline .weaver-after

``capture`` records computed styles via ``css-view`` and is the objective
gate; ``diff`` exits non-zero when any page changed. ``shots`` records
full-page screenshots via ``agent-browser`` for human review, because some
regressions — a wrong icon glyph, a texture that failed to load — are obvious
to the eye and invisible in a style diff.

All three read the published tree under ``public/``, so run ``bun run build``
first. Each serves that tree itself on a local port and stops the server
afterwards, including on failure.
"""

from __future__ import annotations

import contextlib
import difflib
import json
import math
import re
import shutil
import socket
import subprocess
import sys
import time
import typing as typ
import urllib.error
import urllib.request
from pathlib import Path

import cyclopts

if typ.TYPE_CHECKING:
    import collections.abc as cabc

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_WEAVER = REPO_ROOT / "public" / "weaver"
HTTP_SERVER = REPO_ROOT / "node_modules" / ".bin" / "http-server"

# 360 exercises the mobile drawer, 768 the tablet breakpoint, and 1440 the
# fixed-sidebar layout the site was designed against.
SCREENSHOT_WIDTHS = (360, 768, 1440)

# The walker mode's node budget. The largest Weaver page is well under this;
# the ceiling only guards against a runaway capture.
MAX_NODES = 8000

# How long a browser-driving subprocess may take before the run is called off.
# A headless browser that never returns would otherwise hang the snapshot
# indefinitely. Matches the timeout the css-view and Playwright probes in
# tests/ already use for the same tools.
TOOL_TIMEOUT_SECONDS = 90

app = cyclopts.App(
    name="weaver-snapshot",
    help="Capture and compare Weaver computed-style snapshots.",
)


def _page_paths() -> list[str]:
    """List the published Weaver pages as base-relative URL paths.

    Derived from the published tree rather than hard-coded, so a page added to
    ``config/pages.yaml`` is captured without editing this script.

    Returns
    -------
    list of str
        Paths relative to ``/weaver/``, such as ``""`` for the home page and
        ``"commands/act/"`` for a nested one, in sorted order.
    """
    if not PUBLIC_WEAVER.is_dir():
        message = "public/weaver is missing; run 'bun run build' first"
        raise SystemExit(message)
    pages = [
        f"{path.parent.relative_to(PUBLIC_WEAVER).as_posix()}/".removeprefix("./")
        for path in PUBLIC_WEAVER.rglob("index.html")
    ]
    return sorted(pages)


def _slug(page: str) -> str:
    """Turn a page path into a filename stem.

    Parameters
    ----------
    page
        A path relative to ``/weaver/``, such as ``"commands/act/"``.

    Returns
    -------
    str
        A flat, filesystem-safe stem: ``"home"`` for the home page and
        ``"commands__act"`` for the example above.
    """
    return page.strip("/").replace("/", "__") or "home"


@contextlib.contextmanager
def _served(port: int) -> cabc.Iterator[str]:
    """Serve ``public/`` locally for the duration of the context.

    Parameters
    ----------
    port
        TCP port to listen on.

    Yields
    ------
    str
        The base URL of the running server, without a trailing slash.

    Raises
    ------
    SystemExit
        If the port is already occupied, if the server exits while starting,
        or if it does not accept connections within roughly ten seconds.
    """
    if not HTTP_SERVER.is_file():
        message = "node_modules/.bin/http-server is missing; run 'bun install'"
        raise SystemExit(message)

    # Refuse a port somebody else is already serving.
    #
    # `http-server` exits 1 when it cannot bind, but the poll below would then
    # connect to the *pre-existing* server and take it for the one just
    # spawned — silently snapshotting another worktree's `public/` and
    # reporting the diff as this branch's work. The ports are fixed defaults,
    # so two worktrees collide by default rather than by bad luck.
    #
    # Checking `server.poll()` alone would not close this: node needs about a
    # hundred milliseconds to start and fail its bind, and the first request
    # can be answered by the squatter before the child has exited. Probing
    # first makes the common case deterministic; the liveness check below
    # still catches anything that claims the port in between.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as exc:
            message = (
                f"port {port} is already in use, so the snapshot would capture "
                f"whatever is being served there rather than this worktree's "
                f"public/ ({exc}). Stop that server, or pass --port."
            )
            raise SystemExit(message) from exc

    base = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(  # noqa: S603 - fixed argv, no shell, no user input
        [str(HTTP_SERVER), "public", "-p", str(port), "-c-1", "--silent"],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # Poll rather than sleeping a fixed interval, so a slow start does not
        # silently yield a directory full of failed captures.
        for _ in range(50):
            # A server that has already exited will never answer, and anything
            # that does answer on its port is not it.
            if (status := server.poll()) is not None:
                message = (
                    f"http-server exited with status {status} while starting on "
                    f"port {port}; it may have lost a race to bind it"
                )
                raise SystemExit(message)
            try:
                with urllib.request.urlopen(f"{base}/weaver/", timeout=1):  # noqa: S310 - literal loopback URL
                    break
            except (urllib.error.URLError, OSError):
                time.sleep(0.2)
        else:
            message = f"http-server did not come up on port {port}"
            raise SystemExit(message)
        yield base
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # A server that will not stand down still holds the port, and the
            # next run's bind probe would refuse to start because of it.
            server.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                server.wait(timeout=10)


def _prepare_output_dir(out_dir: Path, suffix: str) -> Path:
    """Create the output directory and clear any previous run's files.

    Parameters
    ----------
    out_dir
        Directory to create. Created with parents if absent.
    suffix
        File extension to clear, including the leading dot.

    Returns
    -------
    Path
        The resolved absolute path to the directory.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob(f"*{suffix}"):
        stale.unlink()
    return out_dir.resolve()


def _tool(name: str) -> str:
    """Resolve an external tool to an absolute path.

    Parameters
    ----------
    name
        The executable's name, as it appears on ``PATH``.

    Returns
    -------
    str
        The absolute path to the executable.

    Raises
    ------
    SystemExit
        If the tool is not on ``PATH``, with a message naming it.
    """
    found = shutil.which(name)
    if found is None:
        message = f"{name} is not on PATH"
        raise SystemExit(message)
    return found


@app.command
def capture(out_dir: Path, /, *, port: int = 8099) -> None:
    """Record a computed-style snapshot of every Weaver page.

    Parameters
    ----------
    out_dir
        Directory to write one JSON snapshot per page into. Existing snapshots
        are replaced.
    port
        Port to serve ``public/`` on.
    """
    resolved = _prepare_output_dir(out_dir, ".json")
    pages = _page_paths()
    bun = _tool("bun")
    print(f"capturing {len(pages)} Weaver pages into {resolved}")

    with _served(port) as base:
        for page in pages:
            slug = _slug(page)
            subprocess.run(  # noqa: S603 - fixed argv built from the published tree
                [
                    bun,
                    "x",
                    "css-view",
                    "--mode",
                    "walker",
                    # Pinned rather than left to css-view's default, so a
                    # change to that default cannot swap the engine — and the
                    # rendering — out from under a comparison.
                    "--browser",
                    "chromium",
                    "--max-nodes",
                    str(MAX_NODES),
                    "--wait-until",
                    "networkidle",
                    "--output",
                    str(resolved / f"{slug}.json"),
                    f"{base}/weaver/{page}",
                ],
                cwd=REPO_ROOT,
                check=True,
                stdout=subprocess.DEVNULL,
                timeout=TOOL_TIMEOUT_SECONDS,
            )
            print(f"  {slug}")

    print(f"done: {resolved}")


@app.command
def shots(out_dir: Path, /, *, port: int = 8098) -> None:
    """Record full-page screenshots of every Weaver page at three widths.

    Parameters
    ----------
    out_dir
        Directory to write PNG files into. Existing images are replaced.
    port
        Port to serve ``public/`` on.
    """
    browser = _tool("agent-browser")
    resolved = _prepare_output_dir(out_dir, ".png")
    pages = _page_paths()
    widths = " ".join(str(width) for width in SCREENSHOT_WIDTHS)
    print(f"screenshotting {len(pages)} Weaver pages at {widths} into {resolved}")

    # A dedicated session keeps this clear of any interactive browsing.
    env_session = ["--session", "weaver-shots"]

    def run(*args: str) -> None:
        subprocess.run(  # noqa: S603 - fixed argv built from the published tree
            [browser, *args, *env_session],
            cwd=REPO_ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
            timeout=TOOL_TIMEOUT_SECONDS,
        )

    with _served(port) as base:
        try:
            for width in SCREENSHOT_WIDTHS:
                run("set", "viewport", str(width), "900")
                for page in pages:
                    run("open", f"{base}/weaver/{page}")
                    # The path is positional and must precede the flags:
                    # passing --full first makes agent-browser read the path as
                    # a selector and write the image elsewhere, reporting
                    # success either way. It also runs as a daemon with its own
                    # working directory, so the path must be absolute.
                    run(
                        "screenshot",
                        str(resolved / f"{_slug(page)}@{width}.png"),
                        "--full",
                    )
                print(f"  {width}px done")
        finally:
            with contextlib.suppress(
                subprocess.CalledProcessError, subprocess.TimeoutExpired
            ):
                run("close")

    print(f"done: {resolved}")


# The sRGB transfer function's linear-segment cutoff, from the sRGB
# specification. Named so the conversion below does not read as a magic
# number.
SRGB_LINEAR_CUTOFF = 0.0031308

# Every colour notation handled here takes three components before the
# optional alpha.
COLOUR_COMPONENTS = 3


def _srgb_channel(value: float) -> int:
    """Convert one linear-light channel to an 8-bit sRGB value.

    Parameters
    ----------
    value
        A linear-light channel, nominally in ``[0, 1]`` but allowed to fall
        outside it for colours beyond the sRGB gamut.

    Returns
    -------
    int
        The gamma-encoded channel, clamped to ``[0, 255]``.
    """
    encoded = (
        12.92 * value
        if value <= SRGB_LINEAR_CUTOFF
        else 1.055 * (abs(value) ** (1 / 2.4)) - 0.055
    )
    return max(0, min(255, round(encoded * 255)))


def _oklab_to_rgb(lightness: float, a: float, b: float) -> tuple[int, int, int]:
    """Convert an Oklab colour to 8-bit sRGB.

    Parameters
    ----------
    lightness
        The Oklab ``L`` component, nominally in ``[0, 1]``.
    a, b
        The Oklab opponent components.

    Returns
    -------
    tuple of int
        Red, green, and blue, each in ``[0, 255]``.
    """
    long_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    medium = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    short = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return (
        _srgb_channel(
            4.0767416621 * long_ - 3.3077115913 * medium + 0.2309699292 * short
        ),
        _srgb_channel(
            -1.2684380046 * long_ + 2.6097574011 * medium - 0.3413193965 * short
        ),
        _srgb_channel(
            -0.0041960863 * long_ - 0.7034186147 * medium + 1.7076147010 * short
        ),
    )


# Matches the colour notations Chromium reports in computed values. Tailwind
# v3 resolved an opacity modifier to `rgba(...)`; v4 resolves it through
# `color-mix()` in Oklab and reports `oklab(...)`. The colours are the same to
# within a rounding step, but the strings share not one character.
_COLOUR_FUNCTION = re.compile(
    r"\b(rgba?|oklab|oklch)\(\s*([^)]*)\)",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"-?\d*\.?\d+(?:e-?\d+)?%?")


def _canonical_colour(match: re.Match[str]) -> str:
    """Rewrite one colour function as a canonical 8-bit ``rgba()`` string.

    Parameters
    ----------
    match
        A match of :data:`_COLOUR_FUNCTION`.

    Returns
    -------
    str
        ``rgba(r, g, b, a)`` with integer channels and alpha to three decimal
        places, or the original text if the arguments cannot be read.
    """
    name = match.group(1).lower()
    numbers = _NUMBER.findall(match.group(2))
    if len(numbers) < COLOUR_COMPONENTS:
        return match.group(0)

    def value(index: int, scale: float = 1.0) -> float:
        raw = numbers[index]
        return float(raw.rstrip("%")) / 100 * scale if raw.endswith("%") else float(raw)

    alpha = value(COLOUR_COMPONENTS) if len(numbers) > COLOUR_COMPONENTS else 1.0

    if name.startswith("rgb"):
        red, green, blue = (round(value(i, 255.0)) for i in range(COLOUR_COMPONENTS))
    elif name == "oklab":
        red, green, blue = _oklab_to_rgb(value(0), value(1), value(2))
    else:  # oklch
        chroma, hue = value(1), math.radians(value(2))
        red, green, blue = _oklab_to_rgb(
            value(0), chroma * math.cos(hue), chroma * math.sin(hue)
        )

    return f"rgba({red}, {green}, {blue}, {alpha:.3f})"


def _canonical_value(value: str) -> str:
    """Rewrite every colour function inside one computed value.

    Values such as ``box-shadow`` embed a colour among other components, so
    the substitution is applied in place rather than to the whole string.

    Parameters
    ----------
    value
        A computed property value.

    Returns
    -------
    str
        The value with each colour function in canonical ``rgba()`` form.
    """
    return _COLOUR_FUNCTION.sub(_canonical_colour, value)


# A shadow layer that paints nothing: fully transparent, no offset, no blur,
# no spread. Tailwind composes box-shadow from several `--tw-*` variables and
# v4 uses more of them than v3 did, so the same visible shadow arrives with a
# different number of these placeholders in front of it.
_EMPTY_SHADOW = "rgba(0, 0, 0, 0.000) 0px 0px 0px 0px"

# The alpha channel of a canonicalized `rgba()`, which `_canonical_colour` has
# already normalized to three decimal places by the time this runs.
_SHADOW_ALPHA = re.compile(r"rgba\([^)]*,\s*0\.000\s*\)")


def _is_transparent_shadow(layer: str) -> bool:
    """Report whether a shadow layer paints nothing.

    Alpha decides this on its own. Matching the fully-zero placeholder by its
    exact text missed any transparent layer that carried a geometry — an
    offset, a blur, a spread — even though a shadow at alpha zero is invisible
    whatever its dimensions. Two snapshots then differed over a layer neither
    of them drew.

    Parameters
    ----------
    layer
        One comma-separated layer of a canonicalized shadow value.

    Returns
    -------
    bool
        True when the layer is fully transparent and so paints nothing.
    """
    return layer == _EMPTY_SHADOW or bool(_SHADOW_ALPHA.search(layer))


def _canonical_shadow(value: str) -> str:
    """Drop the placeholder layers from a composed ``box-shadow``.

    Parameters
    ----------
    value
        A canonicalized ``box-shadow`` value.

    Returns
    -------
    str
        The value with every layer that paints nothing removed, or ``"none"``
        if no layer survives.
    """
    # Split on top-level commas only: the layers themselves contain commas,
    # inside their rgba() colour.
    layers: list[str] = []
    buffer = ""
    depth = 0
    for char in value:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            layers.append(buffer.strip())
            buffer = ""
        else:
            buffer += char
    if buffer.strip():
        layers.append(buffer.strip())

    painted = [layer for layer in layers if not _is_transparent_shadow(layer)]
    return ", ".join(painted) if painted else "none"


# The physical and logical names for each border edge, paired so a width can
# be looked up from a colour property and vice versa.
_BORDER_EDGES = (
    ("border-top", "border-block-start"),
    ("border-right", "border-inline-end"),
    ("border-bottom", "border-block-end"),
    ("border-left", "border-inline-start"),
)
_ZERO_WIDTHS = frozenset({"0px", "0", "medium"})


def _drop_invisible_border_colours(style: dict[str, typ.Any]) -> None:
    """Remove the colour of any border edge that is not drawn.

    Tailwind v3's preflight defaulted every border to ``gray-200``; v4 leaves
    it at ``currentColor``. That changes the reported colour on roughly four
    and a half thousand nodes per page, of which only forty draw a border at
    all. Reporting the rest would bury the forty.

    Parameters
    ----------
    style
        A node's computed styles, modified in place.
    """
    for physical, logical in _BORDER_EDGES:
        width = style.get(f"{physical}-width", style.get(f"{logical}-width"))
        # A missing width means the walker saw the user-agent default, which
        # is zero for every element the preflight touches.
        if width is None or width in _ZERO_WIDTHS:
            style.pop(f"{physical}-color", None)
            style.pop(f"{logical}-color", None)


# Properties that take their value from the parent in practice, but which the
# walker compares against the user-agent default instead of against the
# parent. It therefore repeats them on every node in the subtree. `color-scheme`
# is inherited by specification; the rest default to `currentColor` and so
# follow `color` wherever it goes. Set once on `:root`, any of them would
# otherwise be reported five thousand times.
_TRACKS_PARENT = frozenset(
    {
        "color-scheme",
        "outline-color",
        "caret-color",
        "column-rule-color",
        "row-rule-color",
        "text-emphasis-color",
        "-webkit-text-fill-color",
        "-webkit-text-stroke-color",
    }
)


def _normalize(
    node: dict[str, typ.Any],
    inherited: dict[str, typ.Any] | None = None,
) -> dict[str, typ.Any]:
    """Strip incidental variation from one walker node, recursively.

    Seven kinds of variation are incidental here:

    - ``opacity`` on a node running a CSS animation. The Weaver pages carry an
      ``animate-pulse`` status dot whose opacity is sampled mid-cycle.
    - Bounding-box coordinates, which carry subpixel text-shaping jitter.
      Rounding to two decimal places absorbs that without hiding a real
      layout shift.
    - Colour notation. Tailwind v3 resolved `text-primary/80` to `rgba(...)`;
      v4 resolves it through `color-mix()` and Chromium reports `oklab(...)`.
      Comparing the strings would report every translucent colour on the site
      as changed and bury the handful that really did. Each colour is
      therefore converted to 8-bit sRGB before comparison, which is the
      precision a screen has anyway.
    - ``--tw-*`` custom properties. These are Tailwind's own plumbing, and
      which of them exist is an implementation detail of the version in use,
      not something a reader can see.
    - Placeholder ``box-shadow`` layers, for the same reason: v4 composes the
      property from more slots than v3 did, so an unchanged shadow arrives
      behind a different number of fully transparent, zero-size layers.
    - The colour of a border edge with no width. See
      :func:`_drop_invisible_border_colours`.
    - A property in :data:`_TRACKS_PARENT` whose value matches the parent's.
      The walker compares these against the user-agent default rather than
      against the parent, so one declaration on ``:root`` is reported on every
      node beneath it.

    Parameters
    ----------
    node
        A walker-mode node, as emitted by ``css-view``.
    inherited
        The values the parent node carried for the properties in
        :data:`_TRACKS_PARENT`. Empty at the root.

    Returns
    -------
    dict
        The node with those variations removed, and its children likewise.
    """
    style = {
        key: _canonical_value(value) if isinstance(value, str) else value
        for key, value in (node.get("styleDiff") or {}).items()
        if not key.startswith("--tw-")
    }
    if style.get("animation-name", "none") != "none":
        style.pop("opacity", None)
    for key in ("box-shadow", "text-shadow"):
        if isinstance(style.get(key), str):
            style[key] = _canonical_shadow(style[key])
    _drop_invisible_border_colours(style)

    inherited = inherited or {}
    carried = dict(inherited)
    for key in _TRACKS_PARENT & style.keys():
        if style[key] == inherited.get(key):
            del style[key]
        else:
            carried[key] = style[key]

    bbox = node.get("bbox")
    if isinstance(bbox, dict):
        bbox = {
            key: round(value, 2) if isinstance(value, (int, float)) else value
            for key, value in bbox.items()
        }

    normalized = dict(node)
    normalized["styleDiff"] = style
    if bbox is not None:
        normalized["bbox"] = bbox
    normalized["children"] = [
        _normalize(child, carried) for child in node.get("children") or []
    ]
    return normalized


def _normalized_tree(snapshot: Path) -> str:
    """Read a snapshot and render its tree as stable, comparable text.

    Parameters
    ----------
    snapshot
        Path to a ``css-view`` JSON snapshot.

    Returns
    -------
    str
        Pretty-printed JSON with sorted keys, ready to hand to a line differ.
        The capture envelope — URL, timestamp, browser — is dropped, since it
        records when the snapshot was taken, not what the page looks like.
    """
    payload = json.loads(snapshot.read_text(encoding="utf-8"))
    tree = _normalize(payload["payload"]["tree"])
    return json.dumps(tree, indent=2, sort_keys=True, ensure_ascii=False)


@app.command
def diff(before: Path, after: Path, /, *, context: int = 60) -> None:
    """Compare two snapshot directories and report per-page differences.

    Parameters
    ----------
    before
        Directory holding the baseline snapshots.
    after
        Directory holding the snapshots to check.
    context
        Maximum number of diff lines to print per differing page.

    Raises
    ------
    SystemExit
        With status 1 when any page differs, so this can gate a milestone.
    """
    baseline = sorted(before.glob("*.json"))
    if not baseline:
        message = f"no snapshots in {before}"
        raise SystemExit(message)

    differing = 0
    for snapshot in baseline:
        name = snapshot.stem
        candidate = after / snapshot.name
        if not candidate.is_file():
            print(f"{name:<24} MISSING in {after}")
            differing += 1
            continue

        lines = list(
            difflib.unified_diff(
                _normalized_tree(snapshot).splitlines(),
                _normalized_tree(candidate).splitlines(),
                fromfile=str(snapshot),
                tofile=str(candidate),
                lineterm="",
            )
        )
        if not lines:
            print(f"{name:<24} no differences")
            continue

        changed = sum(1 for line in lines[2:] if line[:1] in {"+", "-"})
        print(f"{name:<24} DIFFERS ({changed} changed lines)")
        for line in lines[:context]:
            print(f"    {line}")
        differing += 1

    # A page present only in the after directory is a new page, which is as
    # much a change as an altered one.
    for candidate in sorted(after.glob("*.json")):
        if not (before / candidate.name).is_file():
            print(f"{candidate.stem:<24} NEW in {after}")
            differing += 1

    print(f"{len(baseline)} pages compared, {differing} differing.")
    if differing:
        sys.exit(1)


if __name__ == "__main__":
    app()
