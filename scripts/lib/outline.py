"""1-px dark outline post-process for pixel-art sprites.

Strategy: dilate the alpha mask by 1 px; the ring (dilated XOR original) is the
outline. For each outline pixel, pick an outline colour based on `mode`:

- `palette-darkest` (default): darkest-luminance 8-neighbour colour, further
  darkened 50%. The historical OpenCode/pixel-art default. Punchy, arcade feel.
- `tone-shift`: the 8-neighbour colour darkened only ~20%, giving a softer
  SNES-era "selout" look where outlines are a tonal shift rather than a
  hard black.
- `none`: skip outline entirely.
- `random`: seeded random pick between `palette-darkest` and `tone-shift`
  per-call (used to vary between variants).

Apply before palette quantize so the chosen colour participates in quantize
(snaps to nearest palette entry).

Local-darkness (rather than a single palette-darkest colour) keeps outlines
contextual: a red sprite gets a dark-red outline, a green sprite gets dark-
green, rather than one universal black ring.
"""

from __future__ import annotations

import hashlib
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image as PILImage  # noqa: F401


_NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

VALID_OUTLINE_MODES = ("none", "palette-darkest", "tone-shift", "random")


def _luminance(rgb):
    r, g, b = rgb[0], rgb[1], rgb[2]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _darken_factor(mode: str) -> float:
    """Luminance multiplier for the chosen neighbour colour.

    palette-darkest: 0.5 (legacy, punchy)
    tone-shift:      0.78 (soft SNES-selout feel — darker than body, not black)
    """
    if mode == "tone-shift":
        return 0.78
    return 0.5


def _resolve_random_mode(seed_str: str | None) -> str:
    """Pick a concrete mode for `random`. Seeded when seed_str given."""
    if seed_str is None:
        rng: random.Random = random.Random()
    else:
        h = hashlib.blake2b(seed_str.encode("utf-8"), digest_size=8).digest()
        rng = random.Random(int.from_bytes(h, "big"))
    return rng.choice(["palette-darkest", "tone-shift"])


def add_outline(img, *, mode: str = "palette-darkest", seed_str: str | None = None):
    """Add a 1-px outline ring around the opaque region of an RGBA image.

    Args:
        img: PIL RGBA image (already downscaled to target size).
        mode: one of VALID_OUTLINE_MODES. 'none' returns unchanged.
        seed_str: optional seed for `mode='random'`; makes the choice
            reproducible given the same string.

    Returns: new PIL RGBA image.
    """
    if mode == "none":
        return img
    if mode == "random":
        mode = _resolve_random_mode(seed_str)
    if mode not in ("palette-darkest", "tone-shift"):
        raise ValueError(f"Unknown outline mode '{mode}'. Valid: {VALID_OUTLINE_MODES}")

    from PIL import ImageFilter

    img = img.convert("RGBA")
    w, h = img.size
    pixels = img.load()

    # Binary alpha mask as L-mode image for dilation.
    alpha = img.split()[-1]
    alpha_bin = alpha.point(lambda a: 255 if a >= 128 else 0, mode="L")
    dilated = alpha_bin.filter(ImageFilter.MaxFilter(3))

    bin_px = alpha_bin.load()
    dil_px = dilated.load()

    # Compute global fallback: darkest opaque colour in the sprite.
    global_darkest = None
    global_min_lum = 1e9
    for y in range(h):
        for x in range(w):
            if bin_px[x, y] == 255:
                r, g, b, _ = pixels[x, y]
                lum = _luminance((r, g, b))
                if lum < global_min_lum:
                    global_min_lum = lum
                    global_darkest = (r, g, b)
    if global_darkest is None:
        return img  # nothing opaque, nothing to outline

    factor = _darken_factor(mode)

    def darken(c: int) -> int:
        return max(0, int(c * factor))

    fallback = (
        darken(global_darkest[0]),
        darken(global_darkest[1]),
        darken(global_darkest[2]),
    )

    out = img.copy()
    out_px = out.load()

    for y in range(h):
        for x in range(w):
            if dil_px[x, y] == 255 and bin_px[x, y] == 0:
                # Outline pixel. Find darkest opaque 8-neighbour.
                best = None
                best_lum = 1e9
                for dx, dy in _NEIGHBOURS:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h and bin_px[nx, ny] == 255:
                        r, g, b, _ = pixels[nx, ny]
                        lum = _luminance((r, g, b))
                        if lum < best_lum:
                            best_lum = lum
                            best = (r, g, b)
                color = best if best is not None else fallback
                # Darken the chosen neighbour colour for the outline ring.
                r, g, b = color
                out_px[x, y] = (darken(r), darken(g), darken(b), 255)

    return out
