---
name: ai-pixel-art-image-generation
description: This skill should be used when the user wants to generate images via OpenAI or Azure AI Foundry OR wants to create pixel-art sprites, tileset sheets, walk-cycle animations, tile maps, or other game graphic assets for 2D games. Triggers on "generate image", "create image", "make picture", "draw", "illustrate", and also on "pixel art sprite", "tileset", "spritesheet", "tiled map", "walk cycle", "generate tiles for my game". Handles Azure auth (CLI → DefaultAzureCredential → API key), Gemini 2.5 Flash Image auth (API key) for frame-consistent animation, pixel-art post-processing (nearest-neighbor + palette quantize + optional rembg), and Tiled-compatible TSX/TMJ export.
---

# AI Pixel Art & Tile Map Generator

## Overview

Generate images via OpenAI/Azure AI Foundry and, via an integrated pixel-art pipeline, produce Tiled-compatible pixel-art sprites, tileset sheets, and short sprite-sheet animations for 2D games. The skill covers two user paths:

1. **General image generation** — text-to-image via `gpt-image-2` on OpenAI/Azure.
2. **Pixel-art game-asset mode** — OpenAI/Azure generation + nearest-neighbor downscale + palette quantize + (for animations) Gemini 2.5 Flash Image reference-based frame consistency + TSX/TMJ export for Tiled.

Direct OpenAI uses `OPENAI_API_KEY`. Azure uses `AZURE_OPENAI_ENDPOINT` (or `--endpoint`) plus Azure CLI, `DefaultAzureCredential`, or `AZURE_OPENAI_API_KEY`. Provider selection is `auto`: Azure is used when `AZURE_OPENAI_ENDPOINT` is set, otherwise direct OpenAI is used.

## When to Use Which Script

| Script                         | Use when user wants...                                     |
|--------------------------------|------------------------------------------------------------|
| `scripts/generate_image.py`    | A general-purpose image (any subject, fixed or flexible `gpt-image-2` size). |
| `scripts/generate_sprite.py`   | A single pixel-art sprite (16/32/64 px) with a named palette. |
| `scripts/generate_tileset.py`  | N unique tiles packed into a sheet + TSX + TMJ for Tiled.  |
| `scripts/generate_animation.py`| 2–8 frame sprite-sheet animation (walk/idle) + TSX with `<animation>`. |
| `scripts/pixelize.py`          | Post-process an existing image into pixel art (no generation). |
| `scripts/qa_report.py`         | Standalone QA metrics on an existing pixel-art PNG.        |

All scripts are invokable directly via `python3` and print their output paths on completion.

## Available Image Models

| Model                | Provider         | Use case                           |
|----------------------|------------------|------------------------------------|
| `gpt-image-2`        | OpenAI/Azure     | **Default** — highest quality      |
| `gpt-image-1`        | OpenAI/Azure     | Older generation compatibility     |
| `gpt-image-1-mini`   | OpenAI/Azure     | Faster/cheaper drafts              |
| `sora-2`             | OpenAI/Azure     | Video (not images)                 |

Gemini (separate provider): `gemini-2.5-flash-image` ("Nano Banana") — used for multi-frame animation consistency via reference images.

## Auth

### OpenAI

Use `OPENAI_API_KEY` or `--openai-api-key`.

### Azure

1. **Azure CLI** (`az login`) — tried first; best for local/interactive.
2. **DefaultAzureCredential** — managed identity, env service principal, workload identity.
3. **API key** (`AZURE_OPENAI_API_KEY` or `--api-key`) — fallback for CI/headless.

Install to enable credential auth: `pip install azure-identity`

### Gemini (only for `generate_animation.py`)

API key via `GEMINI_API_KEY` env var (or `--gemini-api-key`). Google has no usable Entra equivalent for this endpoint.

## Dependencies

```bash
pip install openai azure-identity google-genai pillow rembg onnxruntime
```

- `openai`, `azure-identity` → direct OpenAI, Azure auth, and image generation.
- `google-genai` → Gemini reference-image generation (required for `generate_animation.py`).
- `pillow` → post-processing pipeline.
- `rembg` + `onnxruntime` → optional background removal (needed only when `--transparent-bg` is passed; pulls ~100 MB of ONNX runtime).

## Workflows

### 1. General image generation

```bash
python3 ~/.claude/skills/ai-pixel-art-image-generation/scripts/generate_image.py \
  --prompt "a cat on mars, photorealistic" \
  --size 1024x1024 --quality medium \
  --output ~/cat.png
```

Common sizes: `1024x1024`, `1536x1024`, `1024x1536`, `2048x2048`, `2048x1152`, `3840x2160`, `2160x3840`, `auto`. Custom `gpt-image-2` sizes are accepted when they satisfy the model constraints. Qualities: `low`, `medium`, `high`.

### 2. Single pixel-art sprite

```bash
python3 ~/.claude/skills/ai-pixel-art-image-generation/scripts/generate_sprite.py \
  --prompt "orange tabby cat, front view, idle stance" \
  --size 64 --palette db32 --transparent-bg \
  --output ~/cat_64.png
```

- `--size` is the final pixel dimension (square).
- `--palette` is one of: `gameboy`, `pico8`, `db16`, `db32`, `nes`, `aap64`, or `auto`.
- `--palette auto` picks a palette from subject keywords — see the Palette Auto-Pick table.
- `--outline {none,palette-darkest}` — default `palette-darkest`. Adds a 1-px dark ring via alpha dilation → XOR → darkest-luminance neighbour colour before palette quantize.
- `--transparent-bg` runs `rembg` before downscale.
- `--qa` runs QA metrics after save, writes `<output>.qa.json`, and exits non-zero on hard-gate failure.

Output: square RGBA PNG at `--size × --size`, limited to palette colors, hard edges.

### 3. Tileset for Tiled

```bash
python3 ~/.claude/skills/ai-pixel-art-image-generation/scripts/generate_tileset.py \
  --prompt "grass, dirt, stone, water, sand, path, wood plank, stone brick" \
  --tile-size 32 --count 16 --columns 4 --palette pico8 \
  --name overworld --output-dir ~/tilesets/overworld/
```

Comma-separated tile concepts in `--prompt`; repeats if fewer than `--count`. Emits:

- `overworld.png` — packed sheet at `columns*K × rows*K`.
- `overworld.tsx` — Tiled tileset XML with per-tile `name` properties.
- `overworld.tmj` — minimal example map filled with tile 1, openable in Tiled.

Tileset flags:

- `--palette {gameboy,pico8,db16,db32,nes,aap64,auto}` — `auto` picks from keywords (e.g., `"stone"` → `db32`).
- `--seamless {none,crop,torus,auto}` — default `auto`. Pixelizes source at 3× tile size, centre-crops for edge consistency, then if seam_diff ≥ 12.0 runs a torus-wrap feather blend. See `references/seamless.md` (if present) or `lib/seamless.py`.
- `--qa` runs QA metrics (per-tile seam_diff mean, palette fidelity, alpha crispness) and writes a `.qa.json` sidecar.

### 4. Sprite-sheet animation

```bash
python3 ~/.claude/skills/ai-pixel-art-image-generation/scripts/generate_animation.py \
  --prompt "knight with blue cape, side view, walking right" \
  --frames 4 --tile-size 32 --palette db16 \
  --duration-ms 120 --action walk \
  --name knight_walk --output-dir ~/sprites/knight/
```

- Frame 0 is generated via OpenAI/Azure (`gpt-image-2`).
- Frames 1..N use Gemini 2.5 Flash Image with frame 0 as a reference image to maintain character consistency.
- TSX emits an `<animation>` block on tile id 0 that cycles all frames at `--duration-ms`.
- Frame prompts come from `POSE_LIBRARY` in `generate_animation.py`, keyed by `(action, frame_idx, total)`. Supported actions today: `walk` (4 frames, contact/passing/contact-mirror/passing-mirror), `idle` (2 frames), `attack` (4 frames: wind-up/strike/recoil/recovery). Unknown keys fall back to generic `"frame N of M"` phrasing.
- `--qa` runs animation QA (palette fidelity, alpha crispness, `silhouette_iou` between frame 0 and frame 2, `bbox_drift_x`, `bbox_drift_y`) and writes a `.qa.json` sidecar.
- `--transparent-bg` enables rembg on every frame, then applies a **shared** bbox crop across all frames so the character stays aligned frame-to-frame. Per-frame tight-crop would drift position and break the walk-cycle feel.

Consistency caveat: walk cycles may need rerolls. Rerun for different frames if one drifts.

### 5. Post-process an existing image

```bash
python3 ~/.claude/skills/ai-pixel-art-image-generation/scripts/pixelize.py \
  --input raw.png --output sprite.png \
  --size 32 --palette pico8 --transparent-bg
```

## Prompt Engineering

See `references/pixel_art_prompting.md` for detailed guidance. Key rules:

- Include "pixel art sprite, clean hard edges, limited palette, plain flat background, no text, no watermark".
- Specify view angle explicitly ("side view profile", "top-down").
- For tilesets, add "top-down game tile, seamless, centered".
- Avoid "photorealistic", "smooth shading", "gradients".

## Tiled Format Notes

See `references/tiled_format.md`. Quick facts:

- TSX `<image source="...">` is relative to the TSX file — keep PNG + TSX in the same directory.
- TMJ `data` array uses global ids (`firstgid + local_id`). Tile 0 in TSX → gid 1 in TMJ.
- Tile animations declared inline; game engines must re-implement playback at runtime (the `<animation>` tag is metadata).

## Palettes

See `references/palettes.md`. Available: `gameboy` (4), `pico8` (16), `db16` (16), `db32` (32), `nes` (54), `aap64` (64).

### Palette auto-pick

When `--palette auto` is passed, `lib/palettes.suggest_palette` scans the prompt against a keyword table and picks a palette whose colour range matches the subject. Explicit `--palette <name>` always wins. The chosen palette and matched keyword are logged to stderr.

| Keyword pattern                                                                 | Palette   | Why                                             |
|---------------------------------------------------------------------------------|-----------|-------------------------------------------------|
| `metal\|steel\|armor\|stone\|grey\|gray\|silver\|iron\|dungeon\|rock\|brick`    | `db32`    | Mid-greys present; avoids "stone on pico8" fail |
| `tropical\|beach\|coral\|jungle\|aquatic\|underwater\|reef`                     | `aap64`   | Wide warm/cool range for saturated scenes       |
| `gameboy\|monochrome\|green only`                                               | `gameboy` | 4-shade monochrome                              |
| `arcade\|nes\|8-bit\|8bit`                                                      | `nes`     | Canonical NES palette                           |
| `knight\|fantasy\|rpg\|character\|hero\|warrior\|wizard\|mage`                  | `db16`    | DB16 is the canonical RPG-character palette     |
| `terrain\|tile\|overworld\|map\|landscape\|biome`                               | `db32`    | Covers earth/foliage/water tones                |
| `detailed\|portrait\|hi-detail\|high-detail`                                    | `aap64`   | 64 colours support subtle shading               |
| (no match)                                                                      | `db32`    | Default safe choice                             |

## QA metrics and hard gates

When `--qa` is passed to any generator, or via `scripts/qa_report.py <input>`, `lib/qa_metrics` computes the following and writes a `<artifact>.qa.json` sidecar:

| Metric                  | Scope        | Threshold                        | Gate     |
|-------------------------|--------------|----------------------------------|----------|
| `palette_fidelity`      | all          | == 1.0                           | **hard** |
| `alpha_crispness`       | all          | ≥ 0.999                          | **hard** |
| `tile_seam_diff_mean`   | tileset      | ≤ 12.0 (L2 0–255, per-tile mean) | **hard** |
| `silhouette_iou_f0_f2`  | animation    | ≥ 0.85                           | **hard** |
| `bbox_drift_x`          | animation    | ≤ 6 px (walk-cycle leg extension) | **hard** |
| `bbox_drift_y`          | animation    | ≤ 3 px (1–2 px bob allowed)      | **hard** |
| `baseline_alignment`    | sprite       | ≥ 3 contiguous opaque in lowest row | **hard** |
| `outline_coverage`      | sprite       | ≥ 0.85                           | soft     |
| `palette_coverage`      | sprite       | 0.15 ≤ x ≤ 0.60                  | soft     |

Hard failures cause non-zero exit. Standalone re-run:

```bash
python3 ~/.claude/skills/ai-pixel-art-image-generation/scripts/qa_report.py \
  --input ~/tilesets/overworld/overworld.png --kind tileset \
  --palette db32 --tile-size 32 --columns 4
```

## Troubleshooting

- **Azure 401** — CLI token expired (`az login`) or wrong API key.
- **Azure 404** — Deployment name mismatch; verify with `az cognitiveservices account deployment list`.
- **Azure 429** — deployment rate limit hit; wait and retry, or use a different deployment/SKU.
- **Azure ContentFilterError** — Rephrase prompt; Azure content policy violation.
- **Gemini auth error** — `GEMINI_API_KEY` unset; obtain a key from Google AI Studio.
- **Gemini 429 `RESOURCE_EXHAUSTED` on `gemini-2.5-flash-preview-image`** — the image-generation model has **zero free-tier quota**. Upgrade to a paid Google AI Studio plan to use `generate_animation.py`.
- **`rembg` missing** — `pip install rembg onnxruntime`; first run downloads the u2net model (~100 MB).
- **Tileset renders as magenta in Tiled** — image path wrong; ensure PNG and TSX sit side-by-side.
- **Walk cycle frame breaks** — reroll by rerunning with a slightly different action verb ("walking left foot forward").
- **Mushy output** — richer palette, larger `--size`, tighter prompt. See `references/pixel_art_prompting.md`.

## Scope

Supported:

- Tiled TSX/TMJ export, uniform grid sheets, per-tile names, simple frame animations.
- Seamless tiling post-process (3× crop + torus-blend fallback).
- 1-px sprite outlines via dilate-XOR-darkest-neighbour.
- Explicit per-frame pose library for walk/idle/attack animations using frame 0 as the Gemini reference.
- Keyword-based palette auto-pick (`--palette auto`).
- QA metrics with hard-gate exits (`--qa` on any generator, or `scripts/qa_report.py` standalone).

Not in this skill:

- LDtk export, Aseprite `.ase` export.
- Tile bleed/extrude for runtime texture filtering (planned P1).
- Auto-reroll of broken frames, animated tile-scene compositing.
- Autotile / Wang 47-tile blob sets.
