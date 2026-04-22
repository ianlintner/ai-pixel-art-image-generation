"""Seamless tile post-process.

Two strategies:
  1. 'crop' — pixelize source to 3*K x 3*K and return the centre K x K crop.
     Centre of a large consistent surface is closer to tileable than a
     framed single-tile image.
  2. 'torus' — np.roll image by (W//2, H//2), feather-blend the resulting
     centre cross seam across a 2-px window, then re-quantize against the
     palette so colours stay valid. Applied as a fallback when 'crop' alone
     does not satisfy the seam-diff threshold.

The 'auto' policy: run crop, measure seam_diff, if still failing run torus,
re-measure, return the better of the two.
"""

from __future__ import annotations


def seam_diff(img) -> float:
    """Mean L2 RGB distance between wrap-adjacent edge columns/rows.

    Returns scalar on 0-255 scale. Lower is better. < 12.0 is the pass gate.
    """
    import math

    rgba = img.convert("RGBA")
    w, h = rgba.size
    px = rgba.load()

    def rgb_diff(a, b):
        return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)

    total = 0.0
    count = 0
    # Left edge vs. right edge (wrap horizontal).
    for y in range(h):
        total += rgb_diff(px[0, y], px[w - 1, y])
        count += 1
    # Top edge vs. bottom edge (wrap vertical).
    for x in range(w):
        total += rgb_diff(px[x, 0], px[x, h - 1])
        count += 1
    return total / count if count else 0.0


def crop_center(img, tile_size: int):
    """Crop the centre tile_size x tile_size region of img.

    Assumes img is already palette-quantized and sized to a multiple of
    tile_size (typically 3*tile_size).
    """
    w, h = img.size
    left = (w - tile_size) // 2
    top = (h - tile_size) // 2
    return img.crop((left, top, left + tile_size, top + tile_size))


def torus_blend(img, palette_name: str, feather: int = 2):
    """Seam-blend a tile by rolling 50% and feathering the centre cross.

    Applies to the RGB plane only; alpha is preserved. Re-quantizes after
    blend so the output stays palette-valid.
    """
    from PIL import Image

    from lib.palettes import build_palette_image, get_palette

    rgba = img.convert("RGBA")
    w, h = rgba.size

    rgb = rgba.convert("RGB")
    alpha = rgba.split()[-1]

    # np-free roll via PIL crop+paste.
    dx, dy = w // 2, h // 2

    def roll(pil_img, dx, dy):
        # Normalize offsets to [0, w) and [0, h) so reverse rolls (negative dx/dy)
        # still produce valid crop boxes.
        dx %= w
        dy %= h
        out = Image.new(pil_img.mode, pil_img.size)
        if dx == 0 and dy == 0:
            out.paste(pil_img, (0, 0))
            return out
        box = pil_img.crop((0, 0, w, h))
        out.paste(box, (dx, dy))
        # Wrap paste for the parts that went off-edge.
        if dx > 0:
            out.paste(pil_img.crop((w - dx, 0, w, h)), (0, dy))
        if dy > 0:
            out.paste(pil_img.crop((0, h - dy, w, h)), (dx, 0))
        if dx > 0 and dy > 0:
            out.paste(pil_img.crop((w - dx, h - dy, w, h)), (0, 0))
        return out

    rolled = roll(rgb, dx, dy)
    rolled_alpha = roll(alpha, dx, dy)

    # Feather the cross seam at (dx, dy) across `feather` px window.
    px = rolled.load()
    for x in range(w):
        for yo in range(-feather, feather + 1):
            y = dy + yo
            if 0 <= y < h:
                # Blend with neighbour across seam.
                y_other = (y + (-1 if yo > 0 else 1)) % h
                src = px[x, y_other]
                dst = px[x, y]
                t = 0.5 - abs(yo) / (feather * 2 + 2)
                px[x, y] = (
                    int(dst[0] * (1 - t) + src[0] * t),
                    int(dst[1] * (1 - t) + src[1] * t),
                    int(dst[2] * (1 - t) + src[2] * t),
                )
    for y in range(h):
        for xo in range(-feather, feather + 1):
            x = dx + xo
            if 0 <= x < w:
                x_other = (x + (-1 if xo > 0 else 1)) % w
                src = px[x_other, y]
                dst = px[x, y]
                t = 0.5 - abs(xo) / (feather * 2 + 2)
                px[x, y] = (
                    int(dst[0] * (1 - t) + src[0] * t),
                    int(dst[1] * (1 - t) + src[1] * t),
                    int(dst[2] * (1 - t) + src[2] * t),
                )

    # Re-quantize blended RGB against palette.
    pal = build_palette_image(get_palette(palette_name))
    quantized = rolled.quantize(palette=pal, dither=Image.Dither.NONE).convert("RGB")

    # Roll back.
    unrolled = roll(quantized, -dx, -dy)
    unrolled_alpha = roll(rolled_alpha, -dx, -dy)

    out = unrolled.convert("RGBA")
    out.putalpha(unrolled_alpha)
    return out


def edge_match_blend(img, palette_name: str, blend_width: int = None):
    """Force edges to match by averaging opposing edges, then feather inward.

    Stronger than torus_blend for high-contrast tiles. For each row, sets the
    left and right column pixels to their average, then lerps back to
    original content over `blend_width` pixels. Same for top/bottom rows.
    Re-quantizes against the palette to stay palette-valid.

    Args:
        blend_width: pixels over which to fade from forced-average back to
            original. Defaults to max(2, tile_size // 8).
    """
    from PIL import Image

    from lib.palettes import build_palette_image, get_palette

    rgba = img.convert("RGBA")
    w, h = rgba.size
    rgb = rgba.convert("RGB")
    alpha = rgba.split()[-1]

    if blend_width is None:
        blend_width = max(2, min(w, h) // 8)
    blend_width = max(1, min(blend_width, w // 2, h // 2))

    px = rgb.load()

    # Horizontal wrap: force left/right columns equal.
    for y in range(h):
        left_rgb = px[0, y]
        right_rgb = px[w - 1, y]
        avg = tuple((a + b) // 2 for a, b in zip(left_rgb, right_rgb, strict=False))
        for k in range(blend_width):
            t = 1.0 - (k / blend_width)  # t=1 at edge, 0 at blend_width
            lx = k
            rx = w - 1 - k
            for dst_x in (lx, rx):
                src = px[dst_x, y]
                px[dst_x, y] = (
                    int(src[0] * (1 - t) + avg[0] * t),
                    int(src[1] * (1 - t) + avg[1] * t),
                    int(src[2] * (1 - t) + avg[2] * t),
                )

    # Vertical wrap: force top/bottom rows equal.
    for x in range(w):
        top_rgb = px[x, 0]
        bot_rgb = px[x, h - 1]
        avg = tuple((a + b) // 2 for a, b in zip(top_rgb, bot_rgb, strict=False))
        for k in range(blend_width):
            t = 1.0 - (k / blend_width)
            ty = k
            by = h - 1 - k
            for dst_y in (ty, by):
                src = px[x, dst_y]
                px[x, dst_y] = (
                    int(src[0] * (1 - t) + avg[0] * t),
                    int(src[1] * (1 - t) + avg[1] * t),
                    int(src[2] * (1 - t) + avg[2] * t),
                )

    pal = build_palette_image(get_palette(palette_name))
    quantized = rgb.quantize(palette=pal, dither=Image.Dither.NONE).convert("RGB")
    out = quantized.convert("RGBA")
    out.putalpha(alpha)
    return out


def make_seamless(
    tile_img,
    *,
    tile_size: int,
    palette_name: str,
    strategy: str = "auto",
    pass_threshold: float = 12.0,
):
    """Apply seamless strategy and return (result_img, metrics_dict).

    Args:
        tile_img: palette-quantized RGBA image sized exactly tile_size x
            tile_size (the result of pixelize_image with crop applied, OR
            of crop_center on a 3K x 3K source).
        strategy: one of
            - 'none'       : return input unchanged.
            - 'crop'       : assume caller already did the 3x+center-crop; no blend.
            - 'torus'      : center-seam feather blend (half-roll, 2-px feather, re-quantize).
            - 'edge_match' : force opposite edges equal by averaging, feather inward.
            - 'auto'       : try crop; if > threshold try torus; if still > threshold
                             try edge_match; return lowest seam_diff.

    Returns:
        (Image, {'seam_diff_before': float, 'seam_diff_after': float,
                 'strategy_used': str})
    """
    before = seam_diff(tile_img)
    metrics = {"seam_diff_before": before}

    if strategy == "none":
        metrics["strategy_used"] = "none"
        metrics["seam_diff_after"] = before
        return tile_img, metrics

    if strategy == "crop":
        # Caller already did the crop. No further blending.
        metrics["strategy_used"] = "crop"
        metrics["seam_diff_after"] = before
        return tile_img, metrics

    if strategy == "torus":
        blended = torus_blend(tile_img, palette_name)
        after = seam_diff(blended)
        metrics["strategy_used"] = "torus"
        metrics["seam_diff_after"] = after
        return blended, metrics

    if strategy == "edge_match":
        blended = edge_match_blend(tile_img, palette_name)
        after = seam_diff(blended)
        metrics["strategy_used"] = "edge_match"
        metrics["seam_diff_after"] = after
        return blended, metrics

    # auto: crop → torus → edge_match; pick lowest.
    if before < pass_threshold:
        metrics["strategy_used"] = "crop"
        metrics["seam_diff_after"] = before
        return tile_img, metrics

    candidates = [("crop", tile_img, before)]

    torus_img = torus_blend(tile_img, palette_name)
    torus_after = seam_diff(torus_img)
    candidates.append(("torus", torus_img, torus_after))

    if torus_after >= pass_threshold:
        em_img = edge_match_blend(tile_img, palette_name)
        em_after = seam_diff(em_img)
        candidates.append(("edge_match", em_img, em_after))

    # Pick lowest seam_diff.
    candidates.sort(key=lambda x: x[2])
    name, best_img, best_after = candidates[0]
    metrics["strategy_used"] = name
    metrics["seam_diff_after"] = best_after
    return best_img, metrics
