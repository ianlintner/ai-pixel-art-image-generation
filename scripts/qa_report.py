#!/usr/bin/env python3
"""Standalone QA report CLI for pixel-art artifacts.

Wraps lib.qa_metrics.evaluate_{sprite,tileset,animation}. Writes JSON sidecar
next to the input PNG, prints an ASCII table to stdout, and exits non-zero
when any hard gate fails.

Example:
    python3 qa_report.py --input /tmp/cat.png --kind sprite --palette db32
    python3 qa_report.py --input /tmp/overworld.png --kind tileset \
        --palette db32 --tile-size 32 --columns 4 --tile-count 16
    python3 qa_report.py --input /tmp/knight_walk.png --kind animation \
        --palette db16 --tile-size 32 --frames 4
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.palettes import get_palette
from lib.qa_metrics import (
    evaluate_animation,
    evaluate_sprite,
    evaluate_tileset,
    format_report,
)


def parse_args():
    p = argparse.ArgumentParser(description="QA metrics for a pixel-art PNG artifact")
    p.add_argument("--input", required=True, help="Path to PNG")
    p.add_argument("--kind", required=True, choices=["sprite", "tileset", "animation"])
    p.add_argument(
        "--palette",
        required=True,
        help="Palette name (db16/db32/pico8/gameboy/nes/aap64)",
    )
    p.add_argument("--tile-size", type=int, default=32, help="Tile size (tileset/animation)")
    p.add_argument(
        "--columns",
        type=int,
        default=None,
        help="Columns in sheet (tileset; derived from width if omitted)",
    )
    p.add_argument(
        "--tile-count",
        type=int,
        default=None,
        help="Tile count (tileset; derived from dims if omitted)",
    )
    p.add_argument(
        "--frames",
        type=int,
        default=None,
        help="Frame count (animation; derived from width if omitted)",
    )
    p.add_argument(
        "--output-json",
        default=None,
        help="Override JSON sidecar path (default: <input>.qa.json)",
    )
    return p.parse_args()


def main():
    args = parse_args()

    from PIL import Image

    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        print(f"ERROR: input not found: {input_path}", file=sys.stderr)
        sys.exit(2)

    palette_hex = get_palette(args.palette)
    img = Image.open(input_path).convert("RGBA")

    if args.kind == "sprite":
        report = evaluate_sprite(img, palette_hex)

    elif args.kind == "tileset":
        columns = args.columns
        tile_count = args.tile_count
        if columns is None:
            columns = img.size[0] // args.tile_size
        if tile_count is None:
            rows = img.size[1] // args.tile_size
            tile_count = columns * rows
        report = evaluate_tileset(
            img,
            palette_hex,
            tile_size=args.tile_size,
            columns=columns,
            tile_count=tile_count,
        )

    else:  # animation
        frames = args.frames
        if frames is None:
            frames = img.size[0] // args.tile_size
        report = evaluate_animation(
            img,
            palette_hex,
            tile_size=args.tile_size,
            frames=frames,
        )

    report["input"] = str(input_path)
    report["kind"] = args.kind
    report["palette"] = args.palette

    out_json = (
        Path(args.output_json).expanduser().resolve()
        if args.output_json
        else input_path.with_suffix(input_path.suffix + ".qa.json")
    )
    out_json.write_text(json.dumps(report, indent=2, default=_default))

    print(format_report(report))
    print(f"\nJSON: {out_json}")

    if report["hard_fail"]:
        sys.exit(1)


def _default(o):
    if isinstance(o, (set, tuple)):
        return list(o)
    return str(o)


if __name__ == "__main__":
    main()
