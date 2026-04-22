#!/usr/bin/env python3
"""Generate a single pixel-art sprite.

Pipeline: Azure gpt-image-1.5 @ 1024x1024 -> pixelize.py -> PNG at target size.

Example:
    python3 generate_sprite.py \
        --prompt "orange tabby cat, front view, idle stance" \
        --size 64 --palette db32 --transparent-bg \
        --output ~/cat.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.azure_client import build_client, generate_image_bytes, resolve_deployment
from lib.palettes import get_palette, list_palettes, resolve_palette
from lib.qa_metrics import evaluate_sprite, format_report
from pixelize import pixelize_image

SIZE_PROMPT_SUFFIX = (
    " Subject fills the frame edge-to-edge, zoomed in tight with minimal "
    "empty background, centered, plain flat solid-color background, "
    "no text, no watermark, no borders, no shadows on the ground, "
    "pixel art sprite, clean hard edges, limited palette."
)


def parse_args():
    p = argparse.ArgumentParser(
        description="Generate a pixel-art sprite via Azure Foundry + pixelize"
    )
    p.add_argument("--prompt", required=True, help="Subject description")
    p.add_argument(
        "--size",
        type=int,
        default=32,
        help="Target sprite size (square, e.g. 16, 32, 64)",
    )
    p.add_argument(
        "--palette",
        default="db32",
        choices=list_palettes() + ["auto"],
        help="Named palette or 'auto' (pick by subject keyword)",
    )
    p.add_argument("--transparent-bg", action="store_true", help="Remove background via rembg")
    p.add_argument(
        "--outline",
        default="palette-darkest",
        choices=["none", "palette-darkest"],
        help="1-px dark outline ring (default on for sprites)",
    )
    p.add_argument("--output", required=True, help="Output PNG path")
    p.add_argument(
        "--source-size",
        default="1024x1024",
        choices=["1024x1024", "1536x1024", "1024x1536"],
        help="Azure source image size before downscale",
    )
    p.add_argument("--quality", default="high", choices=["low", "medium", "high"])
    p.add_argument("--deployment", default=None, help="Azure deployment name override")
    p.add_argument("--api-key", dest="api_key", help="Force Azure API-key auth")
    p.add_argument("--endpoint", help="Azure endpoint override")
    p.add_argument("--api-version", dest="api_version", help="Azure API version override")
    p.add_argument(
        "--qa",
        action="store_true",
        help="Run QA metrics, write <output>.qa.json, non-zero exit on hard-gate fail",
    )
    return p.parse_args()


def main():
    args = parse_args()

    palette = resolve_palette(args.palette, args.prompt)
    deployment = resolve_deployment(args.deployment)
    client = build_client(
        endpoint=args.endpoint,
        api_key=args.api_key,
        api_version=args.api_version,
        force_api_key=bool(args.api_key),
    )

    full_prompt = args.prompt.rstrip(".") + "." + SIZE_PROMPT_SUFFIX
    print(f"Generating source @ {args.source_size} via {deployment}...")
    images = generate_image_bytes(
        client,
        deployment=deployment,
        prompt=full_prompt,
        size=args.source_size,
        quality=args.quality,
        n=1,
    )

    print(f"Pixelizing to {args.size}x{args.size} with palette '{palette}'...")
    out_img = pixelize_image(
        images[0],
        target_size=args.size,
        palette=palette,
        transparent_bg=args.transparent_bg,
        outline=args.outline,
    )

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_img.save(output_path)
    print(f"Saved: {output_path} ({out_img.size[0]}x{out_img.size[1]} RGBA)")

    if args.qa:
        import json

        report = evaluate_sprite(out_img, get_palette(palette))
        report["input"] = str(output_path)
        report["kind"] = "sprite"
        report["palette"] = palette
        qa_path = output_path.with_suffix(output_path.suffix + ".qa.json")
        qa_path.write_text(json.dumps(report, indent=2, default=str))
        print()
        print(format_report(report))
        print(f"\nJSON: {qa_path}")
        if report["hard_fail"]:
            sys.exit(1)


if __name__ == "__main__":
    main()
