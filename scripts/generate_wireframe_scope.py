"""Generate the wireframe hero's scope scene as SVG.

The scene is one request's path drawn as an X-Y vector display would draw
it: raw bytes funnel into a ``FrameCodec`` plane, frames cross to the
envelope plane, and the router plane deflects the message to one of three
handler terminals. Only the selected route is lit; the other two stay as
dashed underdrawing, because routing selects a handler rather than
broadcasting. Matching magenta marks on the lit handler and the return trace
are the correlation ID.

The geometry is laid out in three dimensions and projected through a pinhole
camera here, at build time, so the browser receives flat paths. Every stroke
is a ``<path>`` of ``M`` and ``L`` commands carrying a ``data-beam`` role; the
scope script reads those paths back and redraws them as a beam. Labels are
SVG text, so the scene is complete with the script, glow, and motion absent.

Run ``uv run python scripts/generate_wireframe_scope.py`` after changing the
scene; ``templates/wireframe/_scope.svg.jinja`` is generated.
"""

from __future__ import annotations

import dataclasses as dc
import math
from pathlib import Path

OUTPUT = Path(__file__).resolve().parents[1] / "templates/wireframe/_scope.svg.jinja"

Point3 = tuple[float, float, float]

# The camera: the flow runs left to right and towards the viewer, so the far
# end of the byte stream recedes and the handlers sit closest.
_YAW = math.radians(-50)
_PITCH = math.radians(6)
_DISTANCE = 21.0
_FOCAL = 520.0
_CENTRE: Point3 = (7.0, 2.0, 0.0)

WIDTH, HEIGHT = 720, 350
_MARGIN = 14


def _camera(p: Point3) -> tuple[float, float, float]:
    """Return ``p`` in camera space: x right, y up, depth away from the eye."""
    x, y, z = (p[0] - _CENTRE[0], p[1] - _CENTRE[1], p[2] - _CENTRE[2])
    x, z = (
        x * math.cos(_YAW) + z * math.sin(_YAW),
        -x * math.sin(_YAW) + z * math.cos(_YAW),
    )
    y, z = (
        y * math.cos(_PITCH) - z * math.sin(_PITCH),
        y * math.sin(_PITCH) + z * math.cos(_PITCH),
    )
    return x, y, _DISTANCE - z


def _raw(p: Point3) -> tuple[float, float]:
    """Project ``p`` to the image plane, before the scene is fitted to the frame."""
    x, y, depth = _camera(p)
    scale = _FOCAL / depth
    return x * scale, -y * scale


@dc.dataclass
class Scene:
    """Strokes and labels in world space, projected on output."""

    strokes: list[tuple[str, list[Point3], str]] = dc.field(default_factory=list)
    labels: list[tuple[Point3, str, str]] = dc.field(default_factory=list)

    def stroke(self, role: str, *points: Point3, extra: str = "") -> None:
        """Add one polyline with a beam role."""
        self.strokes.append((role, list(points), extra))

    def loop(self, role: str, *points: Point3, extra: str = "") -> None:
        """Add a closed polyline."""
        self.stroke(role, *points, points[0], extra=extra)

    def label(self, at: Point3, text: str, css: str = "") -> None:
        """Add a flat text label anchored at a projected point."""
        self.labels.append((at, text, css))


def _lerp(a: Point3, b: Point3, t: float) -> Point3:
    """Return the point ``t`` of the way from ``a`` to ``b``."""
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


def _plane(x: float, y0: float, y1: float, z0: float, z1: float) -> list[Point3]:
    """Return the corners of an upright plane facing along the flow."""
    return [(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)]


def _box(corner: Point3, size: Point3) -> list[list[Point3]]:
    """Return a wireframe box as polylines: two faces and their joining edges."""
    (x, y, z), (w, h, d) = corner, size
    near = [(x, y, z), (x + w, y, z), (x + w, y + h, z), (x, y + h, z), (x, y, z)]
    far = [(px, py, z - d) for px, py, _ in near]
    edges = [[near[i], far[i]] for i in range(4)]
    return [near, far, *edges]


def build() -> Scene:
    """Lay out the scene in world units."""
    s = Scene()

    # Structural underdrawing: a floor grid that the beam barely lights.
    for i in range(-3, 17):
        s.stroke("grid", (i, 0, -2.0), (i, 0, 3.0))
    for k in range(-2, 4):
        s.stroke("grid", (-3, 0, k), (16, 0, k))

    # The byte stream narrows through a funnel to the codec's intake.
    mouth = _plane(-1.5, 0.3, 3.7, -1.7, 1.7)
    throat = _plane(1.8, 1.6, 2.4, -0.4, 0.4)
    s.loop("cyan", *mouth)
    s.loop("cyan", *throat)
    for a, b in zip(mouth, throat, strict=True):
        s.stroke("cyan", a, b)
    for t in (0.33, 0.66):
        ring = [_lerp(m, th, t) for m, th in zip(mouth, throat, strict=True)]
        s.loop("faint", *ring)
    for y in (1.0, 2.0, 3.0):
        s.stroke("bits", (-3.4, y, 0.6), (1.8, 2.0 + (y - 2) * 0.1, 0.0))

    # FrameCodec: an upright plane with the frame it has just cut.
    s.loop("mint", *_plane(2.4, 0.5, 3.5, -1.2, 1.2))
    s.loop("amber", *_plane(2.4, 1.6, 2.4, -0.35, 0.35))
    s.label((2.4, 3.95, 1.1), "FrameCodec", "wf-scope__name")
    s.label((2.4, 3.55, 1.1), "cuts frames", "wf-scope__small")

    # Frames in flight, then the envelope plane.
    for x in (3.0, 4.05, 5.1):
        for line in _box((x, 1.72, 0.28), (0.5, 0.56, 0.56)):
            s.stroke("amber", *line)
    s.loop("mint", *_plane(6.6, 0.7, 3.3, -1.0, 1.0))
    s.loop(
        "magenta",
        (6.6, 2.9, 0.75),
        (6.6, 3.05, 0.6),
        (6.6, 2.9, 0.45),
        (6.6, 2.75, 0.6),
    )
    s.label((6.6, 0.22, 0.95), "Envelope", "wf-scope__name")
    s.label((6.6, -0.2, 0.95), "id 2 · correlation 7", "wf-scope__small")

    # The router: a plane holding the junction rhombus and its decision tree.
    s.loop("mint", *_plane(10.4, 0.2, 3.8, -1.3, 1.3))
    hub = (10.4, 2.0, 0.0)
    s.loop(
        "mint",
        (10.4, 2.55, 0.0),
        (10.4, 2.0, 0.55),
        (10.4, 1.45, 0.0),
        (10.4, 2.0, -0.55),
    )
    s.stroke("faint", (10.4, 2.55, 0.0), (10.4, 1.45, 0.0))
    s.stroke("faint", (10.4, 2.0, 0.55), (10.4, 2.0, -0.55))
    s.label((10.4, 4.25, 1.25), "Router", "wf-scope__name")
    s.label((10.4, 3.85, 1.25), "route by message ID", "wf-scope__small")

    # The lit trace: intake, through every plane, to the selected handler.
    s.stroke(
        "route",
        (-3.4, 2.0, 0.6),
        (2.4, 2.0, 0.0),
        (6.6, 2.0, 0.0),
        hub,
        (13.0, 2.0, 0.0),
        (14.6, 2.0, 0.0),
        extra=' data-pulse="true"',
    )

    # Three handler terminals. One route lit; two left as underdrawing.
    selected = 2.0
    terminals = {"id 1 · login": 3.55, "id 2 · telemetry": 2.0, "id 3 · control": 0.45}
    for name, y in terminals.items():
        lit = y == selected
        face = _plane(14.6, y - 0.6, y + 0.6, -1.7, 1.7)
        s.loop("mint" if lit else "dim", *face)
        if not lit:
            s.stroke(
                "dim", hub, (13.0, y, 0.0), (14.6, y, 0.0), extra=' data-dashed="true"'
            )
        s.label(
            (14.6, y + 0.36, 1.5), name, "wf-scope__name" if lit else "wf-scope__dim"
        )
    s.loop(
        "magenta",
        (14.6, 1.82, -1.25),
        (14.6, 1.97, -1.4),
        (14.6, 1.82, -1.55),
        (14.6, 1.67, -1.4),
    )
    s.stroke("amber", (12.3, 1.72, 0.0), (12.3, 2.28, 0.0))
    s.stroke("amber", (12.6, 1.72, 0.0), (12.6, 2.28, 0.0))
    s.label((12.45, 1.3, 0.6), "middleware", "wf-scope__small")

    # The reply returns along the floor with the same correlation ID.
    s.stroke(
        "return",
        (14.6, 1.45, 0.6),
        (14.6, 0.05, 2.4),
        (2.4, 0.05, 2.4),
        (2.4, 0.5, 1.2),
        extra=' data-dashed="true"',
    )
    s.loop(
        "magenta",
        (11.0, 0.05, 2.7),
        (11.3, 0.05, 2.4),
        (11.0, 0.05, 2.1),
        (10.7, 0.05, 2.4),
    )
    s.label((10.2, -0.45, 3.4), "reply · same correlation ID", "wf-scope__small")
    return s


def _fit(scene: Scene) -> tuple[float, float, float]:
    """Return the scale and offsets that fit the scene into the viewBox."""
    xs, ys = [], []
    for _, points, _ in scene.strokes:
        for p in points:
            x, y = _raw(p)
            xs.append(x)
            ys.append(y)
    scale = min(
        (WIDTH - 2 * _MARGIN) / (max(xs) - min(xs)),
        (HEIGHT - 2 * _MARGIN) / (max(ys) - min(ys)),
    )
    ox = (
        _MARGIN
        - min(xs) * scale
        + (WIDTH - 2 * _MARGIN - (max(xs) - min(xs)) * scale) / 2
    )
    oy = (
        _MARGIN
        - min(ys) * scale
        + (HEIGHT - 2 * _MARGIN - (max(ys) - min(ys)) * scale) / 2
    )
    return scale, ox, oy


_DESCRIPTION = (
    "Bytes funnel into a FrameCodec, which cuts them into frames. The frames"
    " cross to an envelope with message ID 2 and correlation ID 7. The router"
    " matches ID 2 and sends it through middleware to the telemetry handler;"
    " the routes to the login and control handlers stay unlit. The reply"
    " returns along the floor carrying the same correlation ID."
)


def render() -> str:
    """Return the scene as an SVG fragment for the hero template."""
    scene = build()
    scale, ox, oy = _fit(scene)

    def flat(p: Point3) -> str:
        """Format ``p`` as SVG coordinates, fitted to the frame."""
        x, y = _raw(p)
        return f"{x * scale + ox:.1f} {y * scale + oy:.1f}"

    paths = []
    for role, points, extra in scene.strokes:
        d = "M" + " L".join(flat(p) for p in points)
        paths.append(f'    <path data-beam="{role}"{extra} d="{d}"/>')
    labels = []
    for at, text, css in scene.labels:
        x, y = flat(at).split()
        labels.append(f'    <text x="{x}" y="{y}" class="{css}">{text}</text>')
    bits = []
    for row in range(6):
        x, y = flat((-2.9, 3.4 - row * 0.55, 2.9)).split()
        word = format((0b10110010 * (row + 3)) & 0xFF, "08b")
        bits.append(f'    <text x="{x}" y="{y}" class="wf-scope__bits">{word}</text>')

    return "\n".join(
        [
            "{#- Generated by scripts/generate_wireframe_scope.py; edit the script,",
            "    not this file. -#}",
            (
                f'<svg class="wf-scope__svg" viewBox="0 0 {WIDTH} {HEIGHT}" role="img"'
                ' aria-labelledby="scope-title scope-desc">'
            ),
            '  <title id="scope-title">A request routed by message ID</title>',
            f'  <desc id="scope-desc">{_DESCRIPTION}</desc>',
            '  <g class="wf-scope__strokes" aria-hidden="true">',
            *paths,
            "  </g>",
            '  <g class="wf-scope__bitstream" aria-hidden="true">',
            *bits,
            "  </g>",
            '  <g class="wf-scope__labels" aria-hidden="true">',
            *labels,
            "  </g>",
            "</svg>",
            "",
        ]
    )


def main() -> None:
    """Write the scene beside the hero template."""
    OUTPUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
