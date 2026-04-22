#!/usr/bin/env python3
"""Generate a sprite-sheet animation (e.g., 4-frame walk cycle).

Strategy for frame-to-frame consistency:
  1. Azure gpt-image-1.5 generates "frame 0" (the authoritative base pose).
  2. Gemini 2.5 Flash Image generates frames 1..N using frame 0 as a
     reference image with prompts like "same character, walking frame 2/4".
  3. Every frame is pixelized with the same palette so colors stay locked.
  4. Frames are packed horizontally (columns = N, rows = 1). TSX emits an
     <animation> block on tile id 0 so Tiled's animation preview plays.

Caveat: diffusion models drift. Walk cycles may need rerolls. Rerun with
  --frame-seed-offset N to re-roll specific frames.

Example:
    python3 generate_animation.py \
        --prompt "knight walking right" \
        --frames 4 --tile-size 32 --palette db16 \
        --duration-ms 120 --action walk \
        --name knight_walk --output-dir ~/sprites/knight/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_tiled import (
    AnimationFrame,
    TileEntry,
    Tileset,
    write_tsx,
)
from lib.azure_client import build_client, generate_image_bytes, resolve_deployment
from lib.gemini_client import build_client as build_gemini
from lib.gemini_client import generate_with_reference
from lib.palettes import get_palette, list_palettes, resolve_palette
from lib.qa_metrics import evaluate_animation, format_report
from pixelize import pixelize_image

BASE_FRAME_SUFFIX = (
    " pixel art sprite, side view, character fills the frame edge-to-edge "
    "with minimal empty space around silhouette, plain flat solid-color "
    "background, hard edges, limited palette, centered, no text, no watermark, "
    "no ground shadow, contact pose with right leg forward and left leg back, "
    "frame 1 of animation."
)


# Explicit pose descriptors keyed by (action, frame_idx, total_frames).
# Rationale: Gemini treats the reference image as a strong attractor. Using
# "frame N of M" yields near-duplicates. Explicit pose words break the
# attractor along the target axis (walk-cycle theory: contact/passing/
# contact/passing with 1-2px vertical bob on passing frames).
POSE_LIBRARY: dict = {
    ("walk", 0, 4): (
        "contact pose: right leg forward extended, left leg back extended, "
        "body at base height, arms swinging opposite to legs"
    ),
    ("walk", 1, 4): (
        "passing pose: both legs vertical under body crossing, "
        "body raised exactly 1 pixel from base, arms near sides"
    ),
    ("walk", 2, 4): (
        "contact pose mirrored: left leg forward extended, right leg back extended, "
        "body at base height, arms mirrored from frame 1"
    ),
    ("walk", 3, 4): (
        "passing pose mirrored: both legs vertical under body crossing, "
        "body raised 1 pixel from base, arms near sides mirrored"
    ),
    ("idle", 0, 2): "neutral standing pose, body at base height, arms at sides",
    ("idle", 1, 2): "idle breathing pose, body raised exactly 1 pixel, arms at sides",
    ("attack", 0, 4): "wind-up pose: weapon drawn back, body coiled",
    ("attack", 1, 4): "strike pose: weapon extended forward, body leaning into strike",
    ("attack", 2, 4): "recoil pose: weapon past target, body following through",
    ("attack", 3, 4): "recovery pose: weapon returning, body resetting to neutral",
}


def _pose_descriptor(action: str, i: int, total: int) -> str:
    key = (action, i, total)
    if key in POSE_LIBRARY:
        return POSE_LIBRARY[key]
    # Fallback: generic frame-of-total phrasing.
    return f"{action} pose, frame {i + 1} of {total}, mid-motion"


def _frame_prompt(base_prompt: str, action: str, i: int, total: int) -> str:
    pose = _pose_descriptor(action, i, total)
    return (
        f"Same character as the reference image. {pose}. "
        "Exact same silhouette width, same palette, same character facing same direction. "
        "Pixel art sprite, side view, transparent or plain flat background, "
        "hard edges, no text, no watermark."
    )


def parse_args():
    p = argparse.ArgumentParser(description="Generate a pixel-art animation sheet")
    p.add_argument(
        "--prompt",
        required=True,
        help="Character description (e.g. 'knight walking right')",
    )
    p.add_argument("--frames", type=int, default=4, help="Number of frames (>=1)")
    p.add_argument("--tile-size", type=int, default=32)
    p.add_argument(
        "--palette",
        default="db16",
        choices=list_palettes() + ["auto"],
        help="Named palette or 'auto' (pick by subject keyword)",
    )
    p.add_argument(
        "--duration-ms",
        type=int,
        default=120,
        help="Per-frame duration for Tiled <animation>",
    )
    p.add_argument(
        "--action",
        default="walk",
        help="Action verb injected into frame prompts (walk/idle/attack/etc.)",
    )
    p.add_argument(
        "--transparent-bg",
        action="store_true",
        help="Remove background via rembg on each frame",
    )
    p.add_argument("--name", required=True)
    p.add_argument("--output-dir", required=True)
    p.add_argument(
        "--source-size",
        default="1024x1024",
        choices=["1024x1024", "1536x1024", "1024x1536"],
    )
    p.add_argument("--quality", default="high", choices=["low", "medium", "high"])
    p.add_argument("--deployment", default=None)
    p.add_argument("--api-key", dest="api_key")
    p.add_argument("--endpoint")
    p.add_argument("--api-version", dest="api_version")
    p.add_argument(
        "--gemini-api-key",
        dest="gemini_api_key",
        help="Gemini API key (overrides GEMINI_API_KEY env)",
    )
    p.add_argument(
        "--qa",
        action="store_true",
        help="Run QA metrics, write <sheet>.qa.json, non-zero exit on hard-gate fail",
    )
    return p.parse_args()


def main():
    args = parse_args()

    if args.frames < 1:
        print("ERROR: --frames must be >= 1", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    palette = resolve_palette(args.palette, args.prompt)
    deployment = resolve_deployment(args.deployment)
    azure_client = build_client(
        endpoint=args.endpoint,
        api_key=args.api_key,
        api_version=args.api_version,
        force_api_key=bool(args.api_key),
    )

    print(f"[1/{args.frames}] Azure base frame via {deployment}...")
    base_prompt = args.prompt.rstrip(".") + "." + BASE_FRAME_SUFFIX
    base_list = generate_image_bytes(
        azure_client,
        deployment=deployment,
        prompt=base_prompt,
        size=args.source_size,
        quality=args.quality,
        n=1,
    )
    frames_raw: list[bytes] = [base_list[0]]

    if args.frames > 1:
        print(f"  Initializing Gemini client for frames 2..{args.frames}")
        gemini = build_gemini(api_key=args.gemini_api_key)
        for i in range(1, args.frames):
            print(f"[{i + 1}/{args.frames}] Gemini reference-frame generation...")
            prompt = _frame_prompt(args.prompt, args.action, i, args.frames)
            frame_bytes = generate_with_reference(
                gemini,
                prompt=prompt,
                reference_png_bytes=frames_raw[0],
            )
            frames_raw.append(frame_bytes)

    print(f"Pixelizing {len(frames_raw)} frames to {args.tile_size}px palette={palette}...")
    if args.transparent_bg:
        # Shared-bbox crop so all frames align to the same silhouette coords.
        # Per-frame tight-crop would drift the character's position frame to
        # frame (each bbox is independent), which breaks walk-cycle feel and
        # fails bbox_drift / silhouette_iou gates.
        from PIL import Image
        from pixelize import _load_image, _remove_background

        cutouts = [_remove_background(_load_image(raw)) for raw in frames_raw]
        union = None
        for c in cutouts:
            b = c.split()[-1].getbbox()
            if b is None:
                continue
            if union is None:
                union = list(b)
            else:
                union[0] = min(union[0], b[0])
                union[1] = min(union[1], b[1])
                union[2] = max(union[2], b[2])
                union[3] = max(union[3], b[3])
        if union is not None:
            left, top, right, bottom = union
            cw, ch = right - left, bottom - top
            side = max(cw, ch)
            pad = max(1, int(round(side * 0.06)))
            side_padded = side + 2 * pad
            ox_extra = (side - cw) // 2
            oy_extra = (side - ch) // 2
            aligned = []
            for c in cutouts:
                canvas = Image.new("RGBA", (side_padded, side_padded), (0, 0, 0, 0))
                piece = c.crop((left, top, right, bottom))
                canvas.paste(piece, (pad + ox_extra, pad + oy_extra), piece)
                aligned.append(canvas)
            tile_imgs = [
                pixelize_image(
                    c,
                    target_size=args.tile_size,
                    palette=palette,
                    transparent_bg=False,
                    fit_subject=False,
                )
                for c in aligned
            ]
        else:
            tile_imgs = [
                pixelize_image(
                    raw,
                    target_size=args.tile_size,
                    palette=palette,
                    transparent_bg=True,
                    fit_subject=False,
                )
                for raw in frames_raw
            ]
    else:
        tile_imgs = [
            pixelize_image(
                raw,
                target_size=args.tile_size,
                palette=palette,
                transparent_bg=args.transparent_bg,
            )
            for raw in frames_raw
        ]

    from PIL import Image

    sheet = Image.new(
        "RGBA",
        (args.frames * args.tile_size, args.tile_size),
        (0, 0, 0, 0),
    )
    for idx, tile in enumerate(tile_imgs):
        sheet.paste(tile, (idx * args.tile_size, 0))

    image_filename = f"{args.name}.png"
    image_path = out_dir / image_filename
    sheet.save(image_path)
    print(f"Sheet saved: {image_path} ({sheet.size[0]}x{sheet.size[1]})")

    animation = [
        AnimationFrame(tile_id=i, duration_ms=args.duration_ms) for i in range(args.frames)
    ]
    entries = [
        TileEntry(
            tile_id=0,
            name=f"{args.action}_0",
            animation=animation,
        )
    ] + [TileEntry(tile_id=i, name=f"{args.action}_{i}") for i in range(1, args.frames)]

    tileset = Tileset(
        name=args.name,
        tile_size=args.tile_size,
        columns=args.frames,
        tile_count=args.frames,
        image_filename=image_filename,
        image_width=sheet.size[0],
        image_height=sheet.size[1],
        tiles=entries,
    )

    tsx_path = out_dir / f"{args.name}.tsx"
    write_tsx(tileset, tsx_path)
    print(f"TSX saved: {tsx_path}")
    print(
        f"Animation: tile 0 cycles {args.frames} frames @ {args.duration_ms} ms "
        f"(loop duration {args.frames * args.duration_ms} ms)"
    )

    if args.qa:
        import json

        report = evaluate_animation(
            sheet,
            get_palette(palette),
            tile_size=args.tile_size,
            frames=args.frames,
        )
        report["input"] = str(image_path)
        report["kind"] = "animation"
        report["palette"] = palette
        qa_path = image_path.with_suffix(image_path.suffix + ".qa.json")
        qa_path.write_text(json.dumps(report, indent=2, default=str))
        print()
        print(format_report(report))
        print(f"\nJSON: {qa_path}")
        if report["hard_fail"]:
            sys.exit(1)


if __name__ == "__main__":
    main()
