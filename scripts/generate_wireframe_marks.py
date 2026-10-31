"""Draw the wireframe wordmark, symbol, lockup, and favicon as SVG.

The identity specification asks for a lower-case, angular, constructed
wordmark drawn as vector artwork and never rasterized. No production master
exists yet, so this script is the site's master: each glyph is a centreline
polyline on a small grid, and the letter contour is made by masking a narrow
stroke out of a wide one, which leaves a hollow outline of even weight. The
detailed variant adds the construction layer: the centreline skeleton and its
vertex nodes, drawn faintly inside the contour.

Run ``uv run python scripts/generate_wireframe_marks.py`` after changing a
glyph; the files under ``src/static/wireframe/assets/logos/`` are generated.
"""

from __future__ import annotations

import typing as typ
from pathlib import Path

OUTPUT = Path(__file__).resolve().parents[1] / "src/static/wireframe/assets/logos"

MINT = "#7cffb3"
GROUND = "#030e0c"

#: Glyph geometry, in grid units. The baseline is y=60, the x-height y=24,
#: and the ascender y=4. Each glyph is a width and a list of polylines.
Point = tuple[float, float]
GLYPHS: dict[str, tuple[float, list[list[Point]]]] = {
    "w": (30, [[(0, 24), (7, 60), (15, 34), (23, 60), (30, 24)]]),
    "i": (6, [[(3, 24), (3, 60)]]),
    "r": (22, [[(0, 60), (0, 24)], [(0, 32), (8, 24), (22, 24)]]),
    "e": (
        30,
        [
            [
                (3, 42),
                (30, 42),
                (30, 30),
                (24, 24),
                (6, 24),
                (0, 30),
                (0, 54),
                (6, 60),
                (29, 60),
            ]
        ],
    ),
    "f": (24, [[(7, 60), (7, 10), (13, 4), (24, 4)], [(0, 26), (19, 26)]]),
    "a": (
        30,
        [
            [(3, 24), (24, 24), (30, 30), (30, 60)],
            [(30, 42), (6, 42), (0, 48), (0, 54), (6, 60), (30, 60)],
        ],
    ),
    "m": (
        38,
        [
            [(0, 60), (0, 24), (13, 24), (19, 30), (19, 60)],
            [(19, 30), (25, 24), (32, 24), (38, 30), (38, 60)],
        ],
    ),
}

#: The tittle of the i: a small square drawn at contour weight.
TITTLE_SIZE = 6.0
TITTLE_CENTRE_Y = 11.0

OUTER = 8.0  # the full stroke whose edges become the contour
INNER = 4.6  # the stroke masked out of it; walls are (OUTER - INNER) / 2
WALL = (OUTER - INNER) / 2
GAP = 13.0  # space between glyph boxes
WORD = "wireframe"


class Layout(typ.NamedTuple):
    """Placed polylines and tittles for a word, with its total width."""

    lines: list[list[Point]]
    tittles: list[Point]
    width: float


def _layout(word: str) -> Layout:
    """Place each glyph of ``word`` left to right."""
    lines: list[list[Point]] = []
    tittles: list[Point] = []
    x = 0.0
    for letter in word:
        width, polylines = GLYPHS[letter]
        lines.extend([[(x + px, py) for px, py in line] for line in polylines])
        if letter == "i":
            tittles.append((x + 3, TITTLE_CENTRE_Y))
        x += width + GAP
    return Layout(lines, tittles, x - GAP)


def _points(line: list[Point]) -> str:
    """Format a polyline's points attribute."""
    return " ".join(f"{px:g},{py:g}" for px, py in line)


def _strokes(lines: list[list[Point]], width: float, colour: str) -> str:
    """Return polylines stroked at ``width`` in ``colour``."""
    return "".join(
        f'<polyline points="{_points(line)}" fill="none" stroke="{colour}" '
        f'stroke-width="{width:g}" stroke-linecap="square" stroke-linejoin="miter" '
        f'stroke-miterlimit="4"/>'
        for line in lines
    )


def _tittles(centres: list[Point]) -> str:
    """Return the hollow square tittles."""
    half = TITTLE_SIZE / 2
    return "".join(
        f'<rect x="{cx - half:g}" y="{cy - half:g}" width="{TITTLE_SIZE:g}" '
        f'height="{TITTLE_SIZE:g}" fill="none" stroke="{MINT}" '
        f'stroke-width="{WALL:g}"/>'
        for cx, cy in centres
    )


def _contour(layout: Layout, mask_id: str, offset_x: float = 0.0) -> str:
    """Return the masked hollow contour of a laid-out word."""
    shift = f' transform="translate({offset_x:g} 0)"' if offset_x else ""
    return (
        f'<mask id="{mask_id}" maskUnits="userSpaceOnUse">'
        f"<g{shift}>{_strokes(layout.lines, OUTER, '#fff')}"
        f"{_strokes(layout.lines, INNER, '#000')}</g></mask>"
        f'<rect x="-10" y="-10" width="{layout.width + offset_x + 20:g}" height="90" '
        f'fill="{MINT}" mask="url(#{mask_id})"/>'
        f"<g{shift}>{_tittles(layout.tittles)}</g>"
    )


def _skeleton(layout: Layout) -> str:
    """Return the faint construction layer: centrelines and vertex nodes."""
    nodes = {point for line in layout.lines for point in line}
    circles = "".join(
        f'<circle cx="{px:g}" cy="{py:g}" r="0.9" fill="{MINT}"/>'
        for px, py in sorted(nodes)
    )
    return f'<g opacity="0.45">{_strokes(layout.lines, 0.5, MINT)}{circles}</g>'


def _halo(filter_id: str, spread: float) -> str:
    """Return a phosphor-halo filter: a soft bloom behind the crisp core."""
    return (
        f'<filter id="{filter_id}" x="-10%" y="-40%" width="120%" height="180%">'
        f'<feGaussianBlur in="SourceGraphic" stdDeviation="{spread:g}" result="bloom"/>'
        '<feComponentTransfer in="bloom" result="soft">'
        '<feFuncA type="linear" slope="0.55"/></feComponentTransfer>'
        '<feMerge><feMergeNode in="soft"/><feMergeNode in="SourceGraphic"/></feMerge>'
        "</filter>"
    )


def _svg(view_box: str, width: float, height: float, body: str, title: str) -> str:
    """Wrap ``body`` in an accessible SVG document."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}" '
        f'width="{width:g}" height="{height:g}" role="img" aria-label="{title}">'
        f"<title>{title}</title>{body}</svg>\n"
    )


#: The flat wordmark's single stroke, for sizes where a hollow contour's
#: walls would fall below a pixel.
FLAT = 5.0


def _flat(layout: Layout, offset_x: float = 0.0) -> str:
    """Return the flat wordmark: each centreline as one solid stroke."""
    shift = f' transform="translate({offset_x:g} 0)"' if offset_x else ""
    half = TITTLE_SIZE / 2
    tittles = "".join(
        f'<rect x="{cx - half:g}" y="{cy - half:g}" width="{TITTLE_SIZE:g}" '
        f'height="{TITTLE_SIZE:g}" fill="{MINT}"/>'
        for cx, cy in layout.tittles
    )
    return f"<g{shift}>{_strokes(layout.lines, FLAT, MINT)}{tittles}</g>"


def wordmark(*, detailed: bool) -> str:
    """Return the wordmark, detailed or flat.

    The detailed form is the hollow contour with its construction layer; the
    flat form is a single stroke per glyph.
    """
    layout = _layout(WORD)
    pad = OUTER
    view_w = layout.width + 2 * pad
    if detailed:
        body = _halo("halo", 1.6)
        body += f'<g filter="url(#halo)">{_contour(layout, "contour")}</g>'
        body += _skeleton(layout)
    else:
        body = _flat(layout)
    return _svg(f"{-pad:g} -2 {view_w:g} 70", view_w * 2, 140, body, "wireframe")


#: The symbol: a faceted rhombus whose internal beams suggest a framed
#: message crossing a routing junction.
SYMBOL_OUTER: list[Point] = [(4, 32), (32, 6), (60, 32), (32, 58), (4, 32)]
SYMBOL_INNER: list[Point] = [(18, 32), (32, 19), (46, 32), (32, 45), (18, 32)]
SYMBOL_AXES: list[list[Point]] = [[(4, 32), (60, 32)], [(32, 6), (32, 58)]]


def _symbol_body(core: float, detail: float, *, nodes: bool, inner: bool = True) -> str:
    """Return the symbol's strokes at the given weights."""

    def stroke(line: list[Point], width: float, opacity: float = 1.0) -> str:
        return (
            f'<polyline points="{_points(line)}" fill="none" stroke="{MINT}" '
            f'stroke-width="{width:g}" stroke-linejoin="miter" opacity="{opacity:g}"/>'
        )

    body = stroke(SYMBOL_OUTER, core)
    body += "".join(stroke(line, detail, 0.7) for line in SYMBOL_AXES)
    if inner:
        body += stroke(SYMBOL_INNER, detail, 0.85)
    if nodes:
        body += "".join(
            f'<circle cx="{px:g}" cy="{py:g}" r="2.2" fill="{MINT}"/>'
            for px, py in SYMBOL_OUTER[:-1]
        )
    return body


def symbol() -> str:
    """Return the standalone symbol with its halo."""
    body = (
        _halo("halo", 1.4)
        + f'<g filter="url(#halo)">{_symbol_body(2, 1, nodes=True)}</g>'
    )
    return _svg("0 0 64 64", 64, 64, body, "wireframe symbol")


def favicon() -> str:
    """Return the compact icon: a heavier single-colour rhombus on the ground.

    The specification forbids construction lines at 24 to 32px, so only the
    outer rhombus and its axes survive, at a weight that holds at 16px.
    """
    body = f'<rect width="64" height="64" fill="{GROUND}"/>'
    body += _symbol_body(5, 3.5, nodes=False, inner=False)
    return _svg("0 0 64 64", 64, 64, body, "wireframe")


def lockup() -> str:
    """Return the header lockup: the symbol, then the flat wordmark.

    No filter here: the masthead adds a restrained halo in CSS, and the
    lockup must read without it.
    """
    layout = _layout(WORD)
    symbol_scale = 70 / 64
    gap = 14.0
    offset = 64 * symbol_scale + gap + OUTER
    view_w = offset + layout.width + OUTER
    body = (
        f'<g transform="translate(0 -2) scale({symbol_scale:g})">'
        f"{_symbol_body(4, 2, nodes=False, inner=False)}</g>"
        f"{_flat(layout, offset)}"
    )
    return _svg(f"0 -3 {view_w:g} 72", view_w * 2, 144, body, "wireframe")


def render() -> dict[str, str]:
    """Return every mark, keyed by its file name under ``OUTPUT``."""
    return {
        "wordmark-detailed.svg": wordmark(detailed=True),
        "wordmark-simple.svg": wordmark(detailed=False),
        "symbol.svg": symbol(),
        "lockup-horizontal.svg": lockup(),
        "favicon.svg": favicon(),
    }


def main() -> None:
    """Write every mark."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, svg in render().items():
        (OUTPUT / name).write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
