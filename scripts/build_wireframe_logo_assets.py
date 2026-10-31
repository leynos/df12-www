"""Derive the wireframe sub-site's logo assets from the supplied logotype.

The approved logotype is a raster master, ``logotype.png``, drawn as glowing
vector beams on a near-black ground. The site publishes it as artwork rather
than redrawing it, so this script only crops, scales, and keys it.

Keying treats the master as light emitted over black: the alpha of a pixel is
its brightest channel, and its colour is un-premultiplied by that alpha. The
ground becomes transparent, the halo becomes a translucent glow, and the
result composites onto any of the sub-site's dark surfaces without a blend
mode.

Run it from the repository root with the master's path::

    uv run python scripts/build_wireframe_logo_assets.py \
        ../../wireframe-reference/logotype.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

OUTPUT = Path("src/static/wireframe/assets/logos")

# The master's ground is a near-black green, about (0, 4, 0), with faint
# noise in the outer halo; anything at or below this level is treated as unlit.
GROUND = 12
# The outer halo is feathered to nothing over this many pixels at each crop
# edge, so a cropped glow never shows the crop's rectangle.
FEATHER = 48
# Columns 527-561 of the master hold only the symbol's horizontal axis line,
# so the wordmark is cut from the first column after the gap.
WORDMARK_FROM = 548


def _key(rgb: np.ndarray) -> Image.Image:
    """Return an RGBA image whose alpha is the light the master emits."""
    lit = np.clip(rgb.astype(np.float64) - GROUND, 0, None)
    alpha = lit.max(axis=2) / (255 - GROUND)
    safe = np.where(alpha > 0, alpha, 1)[..., None]
    colour = np.clip(lit / (255 - GROUND) / safe * 255, 0, 255)
    rgba = np.dstack([colour, alpha * 255]).round().astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


def _ramp(n: int) -> np.ndarray:
    """Return distance to the nearer end of ``n`` samples, scaled to 0-1."""
    steps = np.arange(n)
    return np.clip(np.minimum(steps, steps[::-1]) / FEATHER, 0, 1)


def _feathered(image: Image.Image) -> Image.Image:
    """Fade the alpha channel to zero towards every edge of ``image``."""
    rgba = np.asarray(image).astype(np.float64)
    h, w = rgba.shape[:2]
    edge = np.outer(_ramp(h), _ramp(w))
    edge = edge * edge * (3 - 2 * edge)
    rgba[..., 3] *= edge
    return Image.fromarray(rgba.round().astype(np.uint8), "RGBA")


def _bounds(rgb: np.ndarray, threshold: int = 24) -> tuple[int, int, int, int]:
    """Return the box around every pixel brighter than ``threshold``."""
    ys, xs = np.nonzero(rgb.max(axis=2) > threshold)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _pad(box: tuple[int, int, int, int], by: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    return left - by, top - by, right + by, bottom + by


def _square(box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    left, top, right, bottom = box
    side = max(right - left, bottom - top)
    cx, cy = (left + right) // 2, (top + bottom) // 2
    return cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2


def _scaled(image: Image.Image, width: int) -> Image.Image:
    height = round(image.height * width / image.width)
    return image.resize((width, height), Image.Resampling.LANCZOS)


def build(master: Path) -> dict[str, Image.Image]:
    """Return the published assets, keyed by file name."""
    rgb = np.asarray(Image.open(master).convert("RGB"))
    lockup = _feathered(_key(rgb).crop(_pad(_bounds(rgb), 40)))

    symbol_rgb = rgb[:, :WORDMARK_FROM]
    symbol_box = _square(_pad(_bounds(symbol_rgb, 60), 12))
    symbol = _key(rgb).crop(symbol_box)

    wordmark_rgb = rgb[:, WORDMARK_FROM:]
    left, top, right, bottom = _pad(_bounds(wordmark_rgb), 40)
    # Blank the symbol, axis line included, before the padded crop reaches it.
    alone = rgb.copy()
    alone[:, : WORDMARK_FROM + 14] = 0
    wordmark = _feathered(
        _key(alone).crop((left + WORDMARK_FROM, top, right + WORDMARK_FROM, bottom))
    )

    # The favicon sits on the canvas colour: browser tabs may be light.
    ground = Image.new("RGBA", symbol.size, (3, 14, 12, 255))
    tile = Image.alpha_composite(ground, symbol)

    return {
        "lockup-1600.webp": _scaled(lockup, 1600),
        "lockup-800.webp": _scaled(lockup, 800),
        "lockup-480.webp": _scaled(lockup, 480),
        "wordmark-1400.webp": _scaled(wordmark, 1400),
        "wordmark-700.webp": _scaled(wordmark, 700),
        "symbol-192.webp": _scaled(symbol, 192),
        "favicon-32.png": _scaled(tile, 32),
        "favicon-48.png": _scaled(tile, 48),
        "apple-touch-icon.png": _scaled(tile, 180).convert("RGB"),
    }


def main() -> None:
    """Write the assets beside the sub-site's other static files."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("master", type=Path, help="path to logotype.png")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, image in build(args.master).items():
        options = {"quality": 92, "method": 6} if name.endswith(".webp") else {}
        image.save(OUTPUT / name, **options)
        print(f"wrote {OUTPUT / name} ({image.width}x{image.height})")


if __name__ == "__main__":
    main()
