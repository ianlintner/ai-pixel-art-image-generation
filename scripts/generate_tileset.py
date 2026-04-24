#!/usr/bin/env python3
"""Generate pixel-art tileset variants with style variation.

Strategy per tileset:
  1. Sample ONE style pick (rendering/lighting/wear/scale) and palette. This
     is critical: per-tile style sampling would produce incompatible tiles.
     Every tile in a given tileset shares the same stylistic suffix.
  2. For each tile concept, call the image API, pixelize, and seamless-process.
  3. Pack into columns × rows PNG; emit TSX + TMJ example + .gen.json sidecar.
  4. --variants N produces N complete tilesets, each in its own subdirectory
     under --output-dir (named <name>_01, <name>_02, ...), each with its
     own sampled style, palette, and sheet.

Example:
    python3 generate_tileset.py \\
        --prompt "grass, dirt, stone, water, sand, path, wood, brick" \\
        --tile-size 32 --count 16 --columns 4 --palette auto \\
        --name overworld --output-dir ~/tilesets/overworld/ \\
        --variants 3 --style hi-bit-snes
"""

from __future__ import annotations

import argparse
import json
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
from lib.palettes import get_palette, jitter_palette, list_palettes, resolve_palette
from lib.prompt_style import (
    STYLE_PRESETS,
    compose_suffix,
    list_style_presets,
    resolve_style,
    rewrite_prompt,
)
from lib.qa_metrics import evaluate_tileset, format_report
from lib.seamless import crop_center, make_seamless, seam_diff
from pixelize import pixelize_image


def parse_args():
    p = argparse.ArgumentParser(description="Generate pixel-art tileset(s) with variation")
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
        default="auto",
        choices=list_palettes() + ["auto"],
        help="Named palette or 'auto' (seeded pick from compatible candidates)",
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

    # -- Variation knobs --
    p.add_argument(
        "--variants",
        "--n",
        dest="variants",
        type=int,
        default=1,
        help="Number of complete tilesets to generate (each in its own subdir)",
    )
    p.add_argument(
        "--style",
        default=None,
        choices=list_style_presets(),
        help="Style preset biasing axis pools",
    )
    p.add_argument(
        "--style-seed",
        default=None,
        help="Override RNG seed for style sampling (default: name + variant index)",
    )
    p.add_argument(
        "--rewrite-prompts",
        action="store_true",
        help="Rephrase each tile concept per tileset via gpt-4.1-mini",
    )
    p.add_argument(
        "--palette-jitter",
        type=float,
        default=0.0,
        help="Per-tileset palette hue/lightness jitter strength 0..1",
    )

    p.add_argument(
        "--source-size",
        default=DEFAULT_IMAGE_SIZE,
        type=validate_image_size,
        metavar="WIDTHxHEIGHT",
        help=f"Source image size before downscale; common values: {', '.join(POPULAR_IMAGE_SIZES)}",
    )
    p.add_argument("--quality", default="high", choices=["low", "medium", "high"])
    p.add_argument(
        "--provider", default=None, choices=VALID_PROVIDERS, help="auto, openai, or azure"
    )
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
        help="Run QA metrics per tileset, non-zero exit on hard-gate fail",
    )
    return p.parse_args()


def split_tile_names(prompt: str, count: int) -> list[str]:
    parts = [p.strip() for p in prompt.split(",") if p.strip()]
    if not parts:
        parts = [prompt.strip()]
    if len(parts) >= count:
        return parts[:count]
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


def _variant_dir(base: Path, name: str, idx: int, total: int) -> Path:
    if total <= 1:
        return base
    width = max(2, len(str(total)))
    return base / f"{name}_{idx:0{width}d}"


def _build_tileset(
    args,
    generator,
    variant_idx: int,
    total_variants: int,
    text_client,
) -> bool:
    """Generate ONE complete tileset. Returns True if QA hard-failed."""
    seed_str = args.style_seed or f"{args.name}|{args.prompt}|{variant_idx}"

    # Palette: seeded pick; preset hint overrides if user asked for auto.
    palette_arg = args.palette
    if palette_arg == "auto" and args.style and args.style in STYLE_PRESETS:
        hint = STYLE_PRESETS[args.style].get("palette_hint")
        if hint:
            palette_arg = hint
    palette_name = resolve_palette(palette_arg, args.prompt, seed_str=seed_str)
    palette_hex = get_palette(palette_name)
    if args.palette_jitter and args.palette_jitter > 0:
        palette_hex = jitter_palette(palette_hex, seed_str=seed_str, strength=args.palette_jitter)

    # Style + suffix: sampled ONCE for the whole tileset.
    style = resolve_style(args.style, seed_str, kind="tile")
    suffix = compose_suffix(style, kind="tile")

    tile_names = split_tile_names(args.prompt, args.count)

    # Optional per-tile prompt rewrite (still one style for the whole set).
    if text_client is not None:
        tile_prompts = [
            rewrite_prompt(text_client, name, variant_idx * args.count + i)
            for i, name in enumerate(tile_names)
        ]
    else:
        tile_prompts = list(tile_names)

    # Output dir per variant (or base dir for single-variant).
    base_out = Path(args.output_dir).expanduser().resolve()
    variant_out = _variant_dir(base_out, args.name, variant_idx + 1, total_variants)
    variant_out.mkdir(parents=True, exist_ok=True)

    print(
        f"\n[tileset variant {variant_idx + 1}/{total_variants}] "
        f"palette={palette_name}{' (jittered)' if args.palette_jitter else ''} "
        f"preset={args.style or 'none'} → {variant_out}"
    )
    print(
        "  style: "
        + ", ".join(
            f"{k}={style[k]}" for k in ("scale", "wear", "rendering", "lighting") if k in style
        )
    )
    print(f"  tiles ({len(tile_names)}): {tile_names}")

    tile_imgs = []
    seam_metrics = []
    for i, (display_name, tile_prompt) in enumerate(zip(tile_names, tile_prompts, strict=False)):
        per_prompt = f"A seamless '{tile_prompt}' surface texture." + suffix
        print(f"    [{i + 1}/{len(tile_names)}] {display_name} ...")
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
                palette=palette_hex,
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
            oversized = pixelize_image(
                raw_list[0],
                target_size=args.tile_size * 3,
                palette=palette_hex,
                transparent_bg=args.transparent_bg,
            )
            cropped = crop_center(oversized, args.tile_size)
            tile, metrics = make_seamless(
                cropped,
                tile_size=args.tile_size,
                palette_name=palette_name,
                strategy=args.seamless,
            )
            seam_metrics.append(metrics)
            print(
                f"      seam_diff: {metrics['seam_diff_before']:.2f} → "
                f"{metrics['seam_diff_after']:.2f} "
                f"(strategy: {metrics['strategy_used']})"
            )
        tile_imgs.append(tile)

    sheet, rows = pack_sheet(tile_imgs, args.columns, args.tile_size)
    image_filename = f"{args.name}.png"
    image_path = variant_out / image_filename
    sheet.save(image_path)
    print(f"  sheet saved: {image_path} ({sheet.size[0]}x{sheet.size[1]})")

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

    tsx_path = variant_out / f"{args.name}.tsx"
    write_tsx(tileset, tsx_path)
    print(f"  TSX saved: {tsx_path}")

    tmj = build_tmj_example(
        tileset,
        tsx_filename=tsx_path.name,
        map_width_tiles=args.map_size,
        map_height_tiles=args.map_size,
    )
    tmj_path = variant_out / f"{args.name}.tmj"
    write_tmj(tmj, tmj_path)
    print(f"  TMJ saved: {tmj_path}")

    # Sidecar for reproducibility.
    sidecar_data = {
        "kind": "tileset",
        "sheet": str(image_path),
        "tsx": str(tsx_path),
        "tmj": str(tmj_path),
        "user_prompt": args.prompt,
        "tile_names": tile_names,
        "tile_prompts": tile_prompts,
        "suffix": suffix,
        "variant_idx": variant_idx,
        "total_variants": total_variants,
        "style_preset": args.style,
        "style_axes": {k: v for k, v in style.items() if not k.startswith("_")},
        "style_extra_clauses": style.get("_extra_clauses") or [],
        "style_seed": seed_str,
        "palette_name": palette_name,
        "palette_jitter": args.palette_jitter,
        "palette_hex": palette_hex,
        "tile_size": args.tile_size,
        "count": args.count,
        "columns": args.columns,
        "source_size": args.source_size,
        "quality": args.quality,
        "seamless": args.seamless,
        "provider": generator.provider,
        "model": generator.model,
        "seam_metrics_per_tile": seam_metrics,
        "rewrite_prompts": args.rewrite_prompts,
    }
    sidecar_path = image_path.with_suffix(image_path.suffix + ".gen.json")
    sidecar_path.write_text(json.dumps(sidecar_data, indent=2, default=str))

    hard_fail = False
    if args.qa:
        report = evaluate_tileset(
            sheet,
            palette_hex,
            tile_size=args.tile_size,
            columns=args.columns,
            tile_count=args.count,
        )
        report["input"] = str(image_path)
        report["kind"] = "tileset"
        report["palette"] = palette_name
        report["palette_hex"] = palette_hex
        report["seam_metrics_per_tile"] = seam_metrics
        qa_path = image_path.with_suffix(image_path.suffix + ".qa.json")
        qa_path.write_text(json.dumps(report, indent=2, default=str))
        print()
        print(format_report(report))
        print(f"  qa JSON: {qa_path}")
        hard_fail = report["hard_fail"]
    return hard_fail


def main():
    args = parse_args()

    if args.variants < 1:
        print("ERROR: --variants must be >= 1", file=sys.stderr)
        sys.exit(2)

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

    text_client = None
    if args.rewrite_prompts:
        try:
            from lib.openai_client import build_client as _build_openai

            text_client = _build_openai(
                api_key=args.openai_api_key,
                organization=args.openai_org,
            )
        except Exception as e:  # noqa: BLE001
            print(
                f"[prompt-rewrite] unavailable, continuing without rewrites: {e}",
                file=sys.stderr,
            )

    any_hard_fail = False
    for v in range(args.variants):
        if _build_tileset(args, generator, v, args.variants, text_client):
            any_hard_fail = True

    if any_hard_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
