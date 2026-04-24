#!/usr/bin/env python3
"""Generate pixel-art sprite variants with style variation.

Pipeline per variant: gpt-image-2 @ source size -> pixelize.py -> PNG.

Variation layers (Tier 1 + Tier 2):
  - Rotated style axes (rendering / lighting / mood / angle / detail) per variant
  - Optional --style preset (chibi, hi-bit-snes, gb-4color, mega-drive,
    modern-indie, nes) biases the axis pools
  - --variants N writes sprite_01.png … sprite_NN.png + .gen.json sidecars
  - --rewrite-prompts calls gpt-4.1-mini to rephrase the subject per variant
  - Seeded palette pick when --palette auto: same prompt+variant_idx → same
    palette; changing either varies it
  - --outline-mode palette-darkest|tone-shift|none|random
  - --palette-jitter 0..1 applies a tiny controlled hue/lightness shift
    per-variant to avoid color-identical outputs

Example:
    python3 generate_sprite.py \\
        --prompt "orange tabby cat, front view, idle stance" \\
        --size 64 --palette auto --transparent-bg \\
        --variants 4 --style modern-indie --palette-jitter 0.05 \\
        --output ~/cats/cat.png
    # → ~/cats/cat_01.png … cat_04.png plus .gen.json sidecars
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.image_client import VALID_PROVIDERS, build_image_generator, generate_image_bytes
from lib.image_options import DEFAULT_IMAGE_SIZE, POPULAR_IMAGE_SIZES, validate_image_size
from lib.outline import VALID_OUTLINE_MODES
from lib.palettes import get_palette, jitter_palette, list_palettes, resolve_palette
from lib.prompt_style import (
    STYLE_PRESETS,
    compose_suffix,
    list_style_presets,
    resolve_style,
    rewrite_prompt,
)
from lib.qa_metrics import evaluate_sprite, format_report
from pixelize import pixelize_image


def parse_args():
    p = argparse.ArgumentParser(description="Generate pixel-art sprite(s) with style variation")
    p.add_argument("--prompt", required=True, help="Subject description")
    p.add_argument(
        "--size",
        type=int,
        default=32,
        help="Target sprite size (square, e.g. 16, 32, 64)",
    )
    p.add_argument(
        "--palette",
        default="auto",
        choices=list_palettes() + ["auto"],
        help="Named palette or 'auto' (seeded pick from compatible candidates)",
    )
    p.add_argument("--transparent-bg", action="store_true", help="Remove background via rembg")
    p.add_argument(
        "--outline",
        default=None,
        choices=list(VALID_OUTLINE_MODES),
        help="1-px outline mode. Default is preset-driven, else 'palette-darkest'.",
    )
    # --outline-mode is an alias for --outline for clarity alongside other "-mode" flags.
    p.add_argument(
        "--outline-mode",
        dest="outline",
        choices=list(VALID_OUTLINE_MODES),
        help=argparse.SUPPRESS,
    )
    p.add_argument("--output", required=True, help="Output PNG path (template for variants)")

    # -- Variation knobs --
    p.add_argument(
        "--variants",
        "--n",
        dest="variants",
        type=int,
        default=1,
        help="Number of sprite variants to generate (writes _01..._NN suffixes)",
    )
    p.add_argument(
        "--style",
        default=None,
        choices=list_style_presets(),
        help="Style preset biasing axis pools (chibi/hi-bit-snes/gb-4color/...)",
    )
    p.add_argument(
        "--style-seed",
        default=None,
        help="Override RNG seed for style sampling (default: prompt + variant index)",
    )
    p.add_argument(
        "--rewrite-prompts",
        action="store_true",
        help="Rephrase the subject per variant via gpt-4.1-mini (adds LLM call)",
    )
    p.add_argument(
        "--palette-jitter",
        type=float,
        default=0.0,
        help="Per-variant palette hue/lightness jitter strength 0..1 (0 disables)",
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
    p.add_argument("--deployment", default=None, help="Image model/deployment override")
    p.add_argument("--model", dest="model", default=None, help=argparse.SUPPRESS)
    p.add_argument("--api-key", dest="api_key", help="Azure API key auth")
    p.add_argument("--openai-api-key", dest="openai_api_key", help="OpenAI API key override")
    p.add_argument("--openai-org", dest="openai_org", help="OpenAI organization override")
    p.add_argument("--endpoint", help="Azure endpoint override")
    p.add_argument("--api-version", dest="api_version", help="Azure API version override")
    p.add_argument(
        "--qa",
        action="store_true",
        help="Run QA metrics per variant, write <output>.qa.json, non-zero exit on hard-gate fail",
    )
    return p.parse_args()


def _variant_output_path(base: Path, idx: int, total: int) -> Path:
    """`cat.png`, idx=3, total=12 → `cat_03.png`. total=1 → unchanged base."""
    if total <= 1:
        return base
    width = max(2, len(str(total)))
    return base.with_stem(f"{base.stem}_{idx:0{width}d}")


def _resolve_default_outline(style_preset: str | None) -> str:
    if style_preset and style_preset in STYLE_PRESETS:
        return STYLE_PRESETS[style_preset].get("outline_default", "palette-darkest")
    return "palette-darkest"


def main():
    args = parse_args()

    if args.variants < 1:
        print("ERROR: --variants must be >= 1", file=sys.stderr)
        sys.exit(2)

    outline_mode = args.outline or _resolve_default_outline(args.style)

    # If user chose --palette auto AND a preset has a palette_hint, use the hint
    # as the starting candidate for deterministic first variant. Still allow
    # seeded variation across variants.
    explicit_palette = args.palette
    if explicit_palette == "auto" and args.style and args.style in STYLE_PRESETS:
        hint = STYLE_PRESETS[args.style].get("palette_hint")
        if hint:
            explicit_palette = hint

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

    base_output = Path(args.output).expanduser().resolve()
    base_output.parent.mkdir(parents=True, exist_ok=True)

    # Lazy-build a text client for prompt rewrites only if needed.
    text_client = None
    if args.rewrite_prompts:
        try:
            from lib.openai_client import build_client as _build_openai

            text_client = _build_openai(
                api_key=args.openai_api_key,
                organization=args.openai_org,
            )
        except Exception as e:  # noqa: BLE001 — rewrite is best-effort
            print(
                f"[prompt-rewrite] unavailable, continuing without rewrites: {e}",
                file=sys.stderr,
            )
            text_client = None

    any_hard_fail = False

    for variant_idx in range(args.variants):
        seed_str = args.style_seed or f"{args.prompt}|{variant_idx}"

        # Resolve palette (may be seeded pick when 'auto' + seed).
        palette_name = resolve_palette(explicit_palette, args.prompt, seed_str=seed_str)
        palette_hex = get_palette(palette_name)
        if args.palette_jitter and args.palette_jitter > 0:
            palette_hex = jitter_palette(
                palette_hex, seed_str=seed_str, strength=args.palette_jitter
            )

        # Resolve style + suffix.
        style = resolve_style(args.style, seed_str, kind="sprite")
        suffix = compose_suffix(style, kind="sprite")

        # Optional prompt rewrite.
        base_prompt = args.prompt
        if text_client is not None:
            base_prompt = rewrite_prompt(text_client, args.prompt, variant_idx)

        full_prompt = base_prompt.rstrip(".") + "." + suffix

        variant_path = _variant_output_path(base_output, variant_idx + 1, args.variants)
        print(
            f"\n[variant {variant_idx + 1}/{args.variants}] {generator.provider}:{generator.model} "
            f"palette={palette_name}{' (jittered)' if args.palette_jitter else ''} "
            f"preset={args.style or 'none'} outline={outline_mode}"
        )
        print(f"  subject: {base_prompt[:80]}{'...' if len(base_prompt) > 80 else ''}")
        print(
            "  style: "
            + ", ".join(
                f"{k}={style[k]}"
                for k in ("angle", "mood", "rendering", "lighting", "detail")
                if k in style
            )
        )

        images = generate_image_bytes(
            generator,
            prompt=full_prompt,
            size=args.source_size,
            quality=args.quality,
            n=1,
        )

        out_img = pixelize_image(
            images[0],
            target_size=args.size,
            palette=palette_hex,
            transparent_bg=args.transparent_bg,
            outline=outline_mode,
            outline_seed=seed_str,
        )

        out_img.save(variant_path)
        print(f"  saved: {variant_path} ({out_img.size[0]}x{out_img.size[1]} RGBA)")

        # Sidecar .gen.json for reproducibility.
        sidecar = variant_path.with_suffix(variant_path.suffix + ".gen.json")
        sidecar_data = {
            "kind": "sprite",
            "output": str(variant_path),
            "user_prompt": args.prompt,
            "variant_prompt": base_prompt,
            "final_prompt": full_prompt,
            "variant_idx": variant_idx,
            "total_variants": args.variants,
            "style_preset": args.style,
            "style_axes": {k: v for k, v in style.items() if not k.startswith("_")},
            "style_extra_clauses": style.get("_extra_clauses") or [],
            "style_seed": seed_str,
            "palette_name": palette_name,
            "palette_jitter": args.palette_jitter,
            "palette_hex": palette_hex,
            "outline_mode": outline_mode,
            "size": args.size,
            "source_size": args.source_size,
            "quality": args.quality,
            "provider": generator.provider,
            "model": generator.model,
            "rewrite_prompts": args.rewrite_prompts,
        }
        sidecar.write_text(json.dumps(sidecar_data, indent=2, default=str))

        if args.qa:
            # QA against the jittered palette is slightly looser than the named
            # palette, but that is intentional: jittered pixels legitimately
            # live in the shifted gamut.
            report = evaluate_sprite(out_img, palette_hex)
            report["input"] = str(variant_path)
            report["kind"] = "sprite"
            report["palette"] = palette_name
            report["palette_hex"] = palette_hex
            qa_path = variant_path.with_suffix(variant_path.suffix + ".qa.json")
            qa_path.write_text(json.dumps(report, indent=2, default=str))
            print()
            print(format_report(report))
            print(f"  qa JSON: {qa_path}")
            if report["hard_fail"]:
                any_hard_fail = True

    if any_hard_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
