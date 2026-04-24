#!/usr/bin/env python3
"""Generate pixel-art animation sheet(s) with style variation.

Strategy for frame-to-frame consistency (unchanged):
  1. gpt-image-2 generates "frame 0" (the authoritative base pose).
  2. Gemini 2.5 Flash Image generates frames 1..N using frame 0 as a
     reference image with explicit pose descriptors.
  3. Every frame is pixelized with the same palette so colours stay locked.
  4. Frames are packed horizontally; TSX emits an <animation> block on tile 0.

Variation (Tier 1 + 2):
  - Style (rendering/lighting/mood/detail) is sampled ONCE per animation set
    and applied to the BASE-FRAME suffix only. Gemini then propagates the
    stylistic look to subsequent frames via the reference image. Per-frame
    style randomization would break silhouette/palette consistency, which is
    load-bearing for walk cycles.
  - --variants N generates N complete animation sets (each a full cycle) in
    per-set subdirectories.
  - --style preset, --palette auto seeded pick, --outline-mode, and
    --palette-jitter all work analogously to generate_sprite.py.

Example:
    python3 generate_animation.py \\
        --prompt "knight walking right" \\
        --frames 4 --tile-size 32 --palette auto \\
        --duration-ms 120 --action walk \\
        --name knight_walk --output-dir ~/sprites/knight/ \\
        --variants 3 --style modern-indie
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from export_tiled import (
    AnimationFrame,
    TileEntry,
    Tileset,
    write_tsx,
)
from lib.gemini_client import build_client as build_gemini
from lib.gemini_client import generate_with_reference
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
from lib.qa_metrics import evaluate_animation, format_report
from pixelize import pixelize_image

# Explicit pose descriptors keyed by (action, frame_idx, total_frames).
# These control per-frame silhouette and are NOT varied by style — they are
# the walk-cycle physics and must stay exact for IoU/bbox_drift gates.
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
    return f"{action} pose, frame {i + 1} of {total}, mid-motion"


def _frame_prompt(action: str, i: int, total: int) -> str:
    pose = _pose_descriptor(action, i, total)
    # Intentionally does NOT inject style axes — the reference image from
    # frame 0 is what locks the style for frames 1..N. Style variation must
    # happen in the BASE frame only.
    return (
        f"Same character as the reference image. {pose}. "
        "Exact same silhouette width, same palette, same character facing same direction. "
        "Pixel art sprite, side view, transparent or plain flat background, "
        "hard edges, no text, no watermark."
    )


def parse_args():
    p = argparse.ArgumentParser(
        description="Generate pixel-art animation sheet(s) with style variation"
    )
    p.add_argument(
        "--prompt",
        required=True,
        help="Character description (e.g. 'knight walking right')",
    )
    p.add_argument("--frames", type=int, default=4, help="Number of frames (>=1)")
    p.add_argument("--tile-size", type=int, default=32)
    p.add_argument(
        "--palette",
        default="auto",
        choices=list_palettes() + ["auto"],
        help="Named palette or 'auto' (seeded pick from compatible candidates)",
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

    # -- Variation knobs --
    p.add_argument(
        "--variants",
        "--n",
        dest="variants",
        type=int,
        default=1,
        help="Number of complete animation sets (each in its own subdir)",
    )
    p.add_argument(
        "--style",
        default=None,
        choices=list_style_presets(),
        help="Style preset biasing axis pools (applied to base frame only)",
    )
    p.add_argument(
        "--style-seed",
        default=None,
        help="Override RNG seed for style sampling (default: name + variant index)",
    )
    p.add_argument(
        "--rewrite-prompts",
        action="store_true",
        help="Rephrase the character subject per variant via gpt-4.1-mini",
    )
    p.add_argument(
        "--palette-jitter",
        type=float,
        default=0.0,
        help="Per-variant palette hue/lightness jitter strength 0..1",
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
        "--gemini-api-key",
        dest="gemini_api_key",
        help="Gemini API key (overrides GEMINI_API_KEY env)",
    )
    p.add_argument(
        "--qa",
        action="store_true",
        help="Run QA metrics per set, non-zero exit on hard-gate fail",
    )
    return p.parse_args()


def _variant_dir(base: Path, name: str, idx: int, total: int) -> Path:
    if total <= 1:
        return base
    width = max(2, len(str(total)))
    return base / f"{name}_{idx:0{width}d}"


def _build_animation(
    args,
    generator,
    variant_idx: int,
    total_variants: int,
    text_client,
) -> bool:
    """Generate ONE complete animation set. Returns True if QA hard-failed."""
    seed_str = args.style_seed or f"{args.name}|{args.prompt}|{variant_idx}"

    palette_arg = args.palette
    if palette_arg == "auto" and args.style and args.style in STYLE_PRESETS:
        hint = STYLE_PRESETS[args.style].get("palette_hint")
        if hint:
            palette_arg = hint
    palette_name = resolve_palette(palette_arg, args.prompt, seed_str=seed_str)
    palette_hex = get_palette(palette_name)
    if args.palette_jitter and args.palette_jitter > 0:
        palette_hex = jitter_palette(palette_hex, seed_str=seed_str, strength=args.palette_jitter)

    # Style sampled ONCE for the whole set. Suffix applied to base frame only.
    style = resolve_style(args.style, seed_str, kind="animation")
    base_suffix = compose_suffix(style, kind="animation")
    # For walk cycles, always assert the contact-pose-frame-1 framing (was
    # baked into the old BASE_FRAME_SUFFIX). Inject after the core suffix so
    # the action pose stays explicit.
    base_suffix += " Contact pose with right leg forward and left leg back, frame 1 of animation."

    # Optional character-level prompt rewrite.
    subject_prompt = args.prompt
    if text_client is not None:
        subject_prompt = rewrite_prompt(text_client, args.prompt, variant_idx)

    base_out = Path(args.output_dir).expanduser().resolve()
    variant_out = _variant_dir(base_out, args.name, variant_idx + 1, total_variants)
    variant_out.mkdir(parents=True, exist_ok=True)

    print(
        f"\n[animation variant {variant_idx + 1}/{total_variants}] "
        f"palette={palette_name}{' (jittered)' if args.palette_jitter else ''} "
        f"preset={args.style or 'none'} → {variant_out}"
    )
    print(
        "  style: "
        + ", ".join(
            f"{k}={style[k]}" for k in ("mood", "rendering", "lighting", "detail") if k in style
        )
    )
    print(f"  subject: {subject_prompt[:80]}{'...' if len(subject_prompt) > 80 else ''}")

    base_prompt = subject_prompt.rstrip(".") + "." + base_suffix
    print(f"  [1/{args.frames}] base frame via {generator.provider}:{generator.model}...")
    base_list = generate_image_bytes(
        generator,
        prompt=base_prompt,
        size=args.source_size,
        quality=args.quality,
        n=1,
    )
    frames_raw: list[bytes] = [base_list[0]]

    if args.frames > 1:
        print(f"  initializing Gemini for frames 2..{args.frames}")
        gemini = build_gemini(api_key=args.gemini_api_key)
        for i in range(1, args.frames):
            print(f"  [{i + 1}/{args.frames}] Gemini reference-frame ...")
            prompt = _frame_prompt(args.action, i, args.frames)
            frame_bytes = generate_with_reference(
                gemini,
                prompt=prompt,
                reference_png_bytes=frames_raw[0],
            )
            frames_raw.append(frame_bytes)

    print(f"  pixelizing {len(frames_raw)} frames @ {args.tile_size}px palette={palette_name}...")
    if args.transparent_bg:
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
                    palette=palette_hex,
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
                    palette=palette_hex,
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
                palette=palette_hex,
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
    image_path = variant_out / image_filename
    sheet.save(image_path)
    print(f"  sheet saved: {image_path} ({sheet.size[0]}x{sheet.size[1]})")

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

    tsx_path = variant_out / f"{args.name}.tsx"
    write_tsx(tileset, tsx_path)
    print(f"  TSX saved: {tsx_path}")
    print(
        f"  animation: tile 0 cycles {args.frames} frames @ {args.duration_ms} ms "
        f"(loop duration {args.frames * args.duration_ms} ms)"
    )

    sidecar_data = {
        "kind": "animation",
        "sheet": str(image_path),
        "tsx": str(tsx_path),
        "user_prompt": args.prompt,
        "variant_prompt": subject_prompt,
        "base_frame_prompt": base_prompt,
        "variant_idx": variant_idx,
        "total_variants": total_variants,
        "style_preset": args.style,
        "style_axes": {k: v for k, v in style.items() if not k.startswith("_")},
        "style_extra_clauses": style.get("_extra_clauses") or [],
        "style_seed": seed_str,
        "palette_name": palette_name,
        "palette_jitter": args.palette_jitter,
        "palette_hex": palette_hex,
        "action": args.action,
        "frames": args.frames,
        "tile_size": args.tile_size,
        "duration_ms": args.duration_ms,
        "source_size": args.source_size,
        "quality": args.quality,
        "provider": generator.provider,
        "model": generator.model,
        "rewrite_prompts": args.rewrite_prompts,
    }
    sidecar_path = image_path.with_suffix(image_path.suffix + ".gen.json")
    sidecar_path.write_text(json.dumps(sidecar_data, indent=2, default=str))

    hard_fail = False
    if args.qa:
        report = evaluate_animation(
            sheet,
            palette_hex,
            tile_size=args.tile_size,
            frames=args.frames,
        )
        report["input"] = str(image_path)
        report["kind"] = "animation"
        report["palette"] = palette_name
        report["palette_hex"] = palette_hex
        qa_path = image_path.with_suffix(image_path.suffix + ".qa.json")
        qa_path.write_text(json.dumps(report, indent=2, default=str))
        print()
        print(format_report(report))
        print(f"  qa JSON: {qa_path}")
        hard_fail = report["hard_fail"]
    return hard_fail


def main():
    args = parse_args()

    if args.frames < 1:
        print("ERROR: --frames must be >= 1", file=sys.stderr)
        sys.exit(1)
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
        if _build_animation(args, generator, v, args.variants, text_client):
            any_hard_fail = True

    if any_hard_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
