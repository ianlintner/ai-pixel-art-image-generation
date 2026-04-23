#!/usr/bin/env python3
"""Generate a tileset: N unique tiles packed into a grid PNG + TSX + TMJ example.

Strategy:
  1. Ask OpenAI/Azure to generate tile concept source images
     with one generation per tile.
  2. Pixelize each source tile/crop to tile_size with chosen palette.
  3. Pack into columns × rows PNG.
  4. Emit TSX with per-tile <properties name="name"/>.
  5. Emit minimal TMJ example filled with tile 1 to preview in Tiled.

Example:
    python3 generate_tileset.py \
        --prompt "grass, dirt, stone, water, sand, path, wood, brick" \
        --tile-size 32 --count 16 --columns 4 --palette pico8 \
        --name overworld --output-dir ~/tilesets/overworld/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_tiled import (
    TileEntry,
    Tileset,
    build_tmj_example,
    write_tmj,
    write_tsx,
)
from lib.image_client import VALID_PROVIDERS, build_image_generator, generate_image_bytes
from lib.image_options import DEFAULT_IMAGE_SIZE, POPULAR_IMAGE_SIZES, validate_image_size
from lib.palettes import get_palette, list_palettes, resolve_palette
from lib.qa_metrics import evaluate_tileset, format_report
from lib.seamless import crop_center, make_seamless, seam_diff
from pixelize import pixelize_image

TILE_PROMPT_SUFFIX = (
    " Part of a large seamless tiling surface, top-down game texture, "
    "uniform coverage, no border, no frame, no UI chrome, "
    "no text, no watermark, flat pixel art, hard edges, limited palette, "
    "transparent or solid flat background."
)


def parse_args():
    p = argparse.ArgumentParser(description="Generate a pixel-art tileset")
    p.add_argument(
        "--prompt",
        required=True,
        help="Comma-separated tile concepts (e.g. 'grass, dirt, stone'). "
        "If fewer than --count, prompt is repeated/expanded.",
    )
    p.add_argument("--tile-size", type=int, default=32, help="Tile size in pixels (square)")
    p.add_argument("--count", type=int, default=16, help="Number of tiles to generate")
    p.add_argument("--columns", type=int, default=4, help="Grid columns (rows derived)")
    p.add_argument(
        "--palette",
        default="pico8",
        choices=list_palettes() + ["auto"],
        help="Named palette or 'auto' (pick by subject keyword)",
    )
    p.add_argument("--transparent-bg", action="store_true", help="Remove backgrounds via rembg")
    p.add_argument(
        "--seamless",
        default="auto",
        choices=["none", "crop", "torus", "edge_match", "auto"],
        help="Seamless strategy: 'auto' tries crop → torus → edge_match, picks lowest seam_diff",
    )
    p.add_argument(
        "--name",
        required=True,
        help="Tileset name (used for filenames and <tileset name=>)",
    )
    p.add_argument("--output-dir", required=True, help="Output directory")
    p.add_argument(
        "--map-size",
        type=int,
        default=10,
        help="TMJ example map dimension (square, in tiles)",
    )
    p.add_argument(
        "--source-size",
        default=DEFAULT_IMAGE_SIZE,
        type=validate_image_size,
        metavar="WIDTHxHEIGHT",
        help=f"Source image size before downscale; common values: {', '.join(POPULAR_IMAGE_SIZES)}",
    )
    p.add_argument("--quality", default="high", choices=["low", "medium", "high"])
    p.add_argument("--provider", default=None, choices=VALID_PROVIDERS, help="auto, openai, or azure")
    p.add_argument("--deployment", default=None)
    p.add_argument("--model", dest="model", default=None, help=argparse.SUPPRESS)
    p.add_argument("--api-key", dest="api_key", help="Azure API key auth")
    p.add_argument("--openai-api-key", dest="openai_api_key", help="OpenAI API key override")
    p.add_argument("--openai-org", dest="openai_org", help="OpenAI organization override")
    p.add_argument("--endpoint")
    p.add_argument("--api-version", dest="api_version")
    p.add_argument(
        "--qa",
        action="store_true",
        help="Run QA metrics, write <sheet>.qa.json, non-zero exit on hard-gate fail",
    )
    return p.parse_args()


def split_tile_names(prompt: str, count: int) -> list[str]:
    parts = [p.strip() for p in prompt.split(",") if p.strip()]
    if not parts:
        parts = [prompt.strip()]
    if len(parts) >= count:
        return parts[:count]
    # Repeat-expand with an index suffix so names are unique
    result: list[str] = []
    i = 0
    while len(result) < count:
        base = parts[i % len(parts)]
        if i < len(parts):
            result.append(base)
        else:
            result.append(f"{base}_{i - len(parts) + 2}")
        i += 1
    return result[:count]


def pack_sheet(tile_images, columns: int, tile_size: int):
    from PIL import Image

    rows = (len(tile_images) + columns - 1) // columns
    sheet = Image.new("RGBA", (columns * tile_size, rows * tile_size), (0, 0, 0, 0))
    for idx, tile in enumerate(tile_images):
        col = idx % columns
        row = idx // columns
        sheet.paste(tile, (col * tile_size, row * tile_size))
    return sheet, rows


def main():
    args = parse_args()

    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    palette = resolve_palette(args.palette, args.prompt)
    model = args.model or args.deployment
    generator = build_image_generator(
        provider=args.provider,
        model=model,
        azure_endpoint=args.endpoint,
        azure_api_key=args.api_key,
        azure_api_version=args.api_version,
        force_azure_api_key=bool(args.api_key),
        openai_api_key=args.openai_api_key,
        openai_organization=args.openai_org,
    )

    tile_names = split_tile_names(args.prompt, args.count)
    print(f"Tiles to generate ({len(tile_names)}): {tile_names}")

    tile_imgs = []
    seam_metrics = []
    for i, name in enumerate(tile_names):
        per_prompt = f"A seamless '{name}' surface texture. {TILE_PROMPT_SUFFIX}"
        print(f"  [{i + 1}/{len(tile_names)}] {name} ...")
        raw_list = generate_image_bytes(
            generator,
            prompt=per_prompt,
            size=args.source_size,
            quality=args.quality,
            n=1,
        )
        if args.seamless == "none":
            tile = pixelize_image(
                raw_list[0],
                target_size=args.tile_size,
                palette=palette,
                transparent_bg=args.transparent_bg,
            )
            seam_metrics.append(
                {
                    "strategy_used": "none",
                    "seam_diff_before": seam_diff(tile),
                    "seam_diff_after": seam_diff(tile),
                }
            )
        else:
            # Pixelize to 3*K x 3*K, crop centre K x K, then (if auto/torus)
            # torus-blend. Centre of a consistent surface tiles cleaner.
            oversized = pixelize_image(
                raw_list[0],
                target_size=args.tile_size * 3,
                palette=palette,
                transparent_bg=args.transparent_bg,
            )
            cropped = crop_center(oversized, args.tile_size)
            tile, metrics = make_seamless(
                cropped,
                tile_size=args.tile_size,
                palette_name=palette,
                strategy=args.seamless,
            )
            seam_metrics.append(metrics)
            print(
                f"    seam_diff: {metrics['seam_diff_before']:.2f} → "
                f"{metrics['seam_diff_after']:.2f} "
                f"(strategy: {metrics['strategy_used']})"
            )
        tile_imgs.append(tile)

    sheet, rows = pack_sheet(tile_imgs, args.columns, args.tile_size)
    image_filename = f"{args.name}.png"
    image_path = out_dir / image_filename
    sheet.save(image_path)
    print(f"\nSheet saved: {image_path} ({sheet.size[0]}x{sheet.size[1]})")

    entries = [TileEntry(tile_id=i, name=tile_names[i]) for i in range(len(tile_names))]

    tileset = Tileset(
        name=args.name,
        tile_size=args.tile_size,
        columns=args.columns,
        tile_count=args.count,
        image_filename=image_filename,
        image_width=sheet.size[0],
        image_height=sheet.size[1],
        tiles=entries,
    )

    tsx_path = out_dir / f"{args.name}.tsx"
    write_tsx(tileset, tsx_path)
    print(f"TSX saved: {tsx_path}")

    tmj = build_tmj_example(
        tileset,
        tsx_filename=tsx_path.name,
        map_width_tiles=args.map_size,
        map_height_tiles=args.map_size,
    )
    tmj_path = out_dir / f"{args.name}.tmj"
    write_tmj(tmj, tmj_path)
    print(f"TMJ saved: {tmj_path}")

    if args.qa:
        import json

        report = evaluate_tileset(
            sheet,
            get_palette(palette),
            tile_size=args.tile_size,
            columns=args.columns,
            tile_count=args.count,
        )
        report["input"] = str(image_path)
        report["kind"] = "tileset"
        report["palette"] = palette
        report["seam_metrics_per_tile"] = seam_metrics
        qa_path = image_path.with_suffix(image_path.suffix + ".qa.json")
        qa_path.write_text(json.dumps(report, indent=2, default=str))
        print()
        print(format_report(report))
        print(f"\nJSON: {qa_path}")
        if report["hard_fail"]:
            sys.exit(1)


if __name__ == "__main__":
    main()
