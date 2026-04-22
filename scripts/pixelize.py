#!/usr/bin/env python3
"""Pixelize post-process pipeline.

Steps:
  1. Optional background removal via rembg (u2net).
  2. Two-stage downscale: Lanczos to 2x target, then nearest-neighbor to target.
  3. Palette quantize against named palette (PIL Image.quantize).
  4. Alpha threshold binarization so sprite edges stay crisp.
  5. Save RGBA PNG.

Usable standalone:
  python3 pixelize.py --input raw.png --output sprite.png --size 64 --palette db32 --transparent-bg

Or imported:
  from pixelize import pixelize_image
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.palettes import build_palette_image, get_palette, list_palettes


def _remove_background(img):
    try:
        from rembg import remove  # type: ignore
    except ImportError:
        print(
            "ERROR: rembg not installed. Run: pip install rembg onnxruntime",
            file=sys.stderr,
        )
        sys.exit(1)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return _load_image(remove(buf.getvalue()))


def _load_image(src: bytes | str | Path | Image.Image):
    if isinstance(src, Image.Image):
        return src.convert("RGBA")
    if isinstance(src, (bytes, bytearray)):
        return Image.open(io.BytesIO(src)).convert("RGBA")
    return Image.open(src).convert("RGBA")


def _tight_crop_square(img, pad_frac: float = 0.06):
    """Crop to opaque bbox, pad to square, return subject-centred square image.

    Pixel-art sprites should fill their frame. After rembg, the subject sits
    wherever the diffusion model placed it in the source canvas — often with
    large transparent margins. Cropping to the alpha bbox and padding the
    short axis to a square recovers resolution when the frame is then resized
    to target size.

    Args:
        img: RGBA image (expected post-rembg, so alpha is a clean cutout).
        pad_frac: fractional padding around the bbox, relative to the longer
            subject dimension. 0.06 = ~6% breathing room so the outline pass
            has room to write pixels without being clipped.

    Returns:
        RGBA Image that is square (side = longer_dim + 2*pad), subject
        centred, transparent padding. If img has no opaque pixels, returns
        img unchanged.
    """
    alpha = img.split()[-1]
    bbox = alpha.getbbox()
    if bbox is None:
        return img

    left, top, right, bottom = bbox
    cw = right - left
    ch = bottom - top
    long_side = max(cw, ch)
    pad = max(1, int(round(long_side * pad_frac)))
    side = long_side + 2 * pad

    cropped = img.crop(bbox)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    ox = (side - cw) // 2
    oy = (side - ch) // 2
    canvas.paste(cropped, (ox, oy), cropped)
    return canvas


def _quantize_rgba(img, palette_name: str):
    """Quantize an RGBA image to the palette, preserving alpha."""
    palette_img = build_palette_image(get_palette(palette_name))

    rgb = img.convert("RGB")
    # Convert to P using the supplied palette. Requires P-mode palette source.
    quantized = rgb.quantize(palette=palette_img, dither=Image.Dither.NONE)
    quantized_rgb = quantized.convert("RGB")

    alpha = img.split()[-1]
    # Alpha threshold: binarize at 128 to avoid semi-transparent garbage.
    alpha_bin = alpha.point(lambda a: 255 if a >= 128 else 0, mode="L")

    out = quantized_rgb.convert("RGBA")
    out.putalpha(alpha_bin)
    return out


def pixelize_image(
    src,
    *,
    target_size: int | tuple[int, int],
    palette: str,
    transparent_bg: bool = False,
    outline: str = "none",
    fit_subject: bool = True,
    subject_pad_frac: float = 0.06,
) -> Image.Image:
    """Run the full pixelize pipeline and return a PIL Image.

    Args:
        outline: 'none' or 'palette-darkest'. Applied after NN downscale,
            before palette quantize so outline colours snap to palette.
        fit_subject: when transparent_bg is True, tight-crop the subject to
            its alpha bbox and pad to a square so it fills the output frame.
            Ignored when transparent_bg is False (tileset textures should
            occupy the full source area).
        subject_pad_frac: breathing room around the subject bbox (fraction
            of the longer subject dimension). ~6% gives the outline pass a
            pixel or two of margin without wasting frame.
    """
    if isinstance(target_size, int):
        target = (target_size, target_size)
    else:
        target = target_size

    img = _load_image(src)

    if transparent_bg:
        img = _remove_background(img)
        if fit_subject:
            img = _tight_crop_square(img, pad_frac=subject_pad_frac)

    # Two-stage downscale: Lanczos to 2x target, then nearest to target.
    intermediate = (target[0] * 2, target[1] * 2)
    if img.size != intermediate:
        img = img.resize(intermediate, Image.LANCZOS)
    img = img.resize(target, Image.NEAREST)

    if outline != "none":
        from lib.outline import add_outline

        img = add_outline(img, mode=outline)

    return _quantize_rgba(img, palette)


def parse_args():
    p = argparse.ArgumentParser(description="Pixelize an image: downscale + palette quantize")
    p.add_argument("--input", required=True, help="Source image path")
    p.add_argument("--output", required=True, help="Output PNG path")
    p.add_argument(
        "--size",
        type=int,
        required=True,
        help="Target pixel size (square, e.g. 32 for 32x32)",
    )
    p.add_argument(
        "--palette",
        required=True,
        choices=list_palettes(),
        help="Named palette for quantization",
    )
    p.add_argument(
        "--transparent-bg",
        action="store_true",
        help="Remove background via rembg before downscale",
    )
    p.add_argument(
        "--outline",
        default="none",
        choices=["none", "palette-darkest"],
        help="Optional 1-px dark outline ring (sprites only)",
    )
    return p.parse_args()


def main():
    args = parse_args()
    out = pixelize_image(
        args.input,
        target_size=args.size,
        palette=args.palette,
        transparent_bg=args.transparent_bg,
        outline=args.outline,
    )
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(output_path)
    print(f"Saved: {output_path} ({out.size[0]}x{out.size[1]} RGBA, palette={args.palette})")


if __name__ == "__main__":
    main()
