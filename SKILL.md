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

**Endpoint gotcha.** Azure AI Foundry resources expose two URLs. Use the **Azure OpenAI legacy endpoint** for `gpt-image-*`, not the AI Services endpoint:

- ✅ `https://<resource>.openai.azure.com/` — works with `scripts/lib/azure_client.py`.
- ❌ `https://<resource>.services.ai.azure.com/` — Foundry-native API, not compatible with this skill.

Discover it with:
```bash
az cognitiveservices account show --name <resource> --resource-group <rg> \
  --query 'properties.endpoints' -o json
```

**Provider auto-select.** Provider resolves to `azure` when `AZURE_OPENAI_ENDPOINT` is set in the environment. Some shells/tools (e.g. agent runners) don't source `~/.zshrc`; if `--provider auto` falls back to OpenAI unexpectedly, either prefix the call (`AZURE_OPENAI_ENDPOINT=... python scripts/…`) or pass `--provider azure --endpoint https://…` explicitly.

### Deploying a model on Azure

Before first use you need a deployment of the image model on your resource. The `az cognitiveservices account deployment create` extension has a bug where it pins an unsupported `api-version`. Use `az rest` directly:

```bash
SUB=$(az account show --query id -o tsv)
RG=$(az cognitiveservices account list \
       --query "[?name=='<resource>'].resourceGroup" -o tsv)

az rest --method put \
  --url "https://management.azure.com/subscriptions/${SUB}/resourceGroups/${RG}/providers/Microsoft.CognitiveServices/accounts/<resource>/deployments/gpt-image-2?api-version=2024-10-01" \
  --body '{"sku":{"name":"GlobalStandard","capacity":1},"properties":{"model":{"format":"OpenAI","name":"gpt-image-2","version":"2026-04-21"}}}'
```

Check what's deployable in your region first:
```bash
az cognitiveservices model list --location <region> \
  --query "[?kind=='OpenAI' && starts_with(model.name,'gpt-image')].{name:model.name,version:model.version}" -o table
```

**Regional availability (as of 2026-04).** `gpt-image-2` (version `2026-04-21`) is only published in `eastus2`. `gpt-image-1`, `gpt-image-1-mini`, and `gpt-image-1.5` are more broadly available. If your resource lives elsewhere, either deploy `gpt-image-1.5` (newest broadly-available) or create a second resource in `eastus2`.

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
- **Azure 404 `DeploymentNotFound`** — Deployment name mismatch; verify with `az cognitiveservices account deployment list -n <resource> -g <rg>`. If the model *exists* in the region but isn't deployed yet, create the deployment (see "Deploying a model on Azure" above).
- **Azure 404 from AI Services endpoint** — you're pointing at `https://<resource>.services.ai.azure.com/` instead of `https://<resource>.openai.azure.com/`. The skill's client needs the legacy OpenAI endpoint.
- **Azure 429** — deployment rate limit hit; default rate on fresh GlobalStandard image deployments is ~1 req/60s at capacity 1. Bump capacity via the same `az rest` deploy command (PATCH with higher `sku.capacity`) or wait between generations.
- **Azure `api-version` error on `deployment create`** — the CLI extension pins `2025-09-01` which Azure rejects and ignores `--api-version`. Use the `az rest` workaround in "Deploying a model on Azure".
- **Azure ContentFilterError** — Rephrase prompt; Azure content policy violation.
- **`ERROR: OpenAI provider requires OPENAI_API_KEY` when you expected Azure** — `AZURE_OPENAI_ENDPOINT` isn't in the process env (shell didn't source `~/.zshrc`, or the runner strips it). Prefix inline: `AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/ python scripts/…` or pass `--provider azure --endpoint …`.
- **Gemini auth error** — `GEMINI_API_KEY` unset; obtain a key from Google AI Studio.
- **Gemini 429 `RESOURCE_EXHAUSTED` on `gemini-2.5-flash-preview-image`** — the image-generation model has **zero free-tier quota**. Upgrade to a paid Google AI Studio plan to use `generate_animation.py`.
- **`rembg` missing** — `pip install rembg onnxruntime`; first run downloads the u2net model (~100 MB).
- **Tileset renders as magenta in Tiled** — image path wrong; ensure PNG and TSX sit side-by-side.
- **Walk cycle frame breaks** — reroll by rerunning with a slightly different action verb ("walking left foot forward").
- **Mushy output** — richer palette, larger `--size`, tighter prompt. See `references/pixel_art_prompting.md`.
- **QA `outline_coverage` soft-fail at 32px low quality** — expected. The model doesn't reliably draw 1-px outlines at small sizes. Either raise `--quality medium`, increase `--size 64`, or rely on `--outline palette-darkest` post-process (default) which adds the ring deterministically.
- **QA `palette_coverage` soft-fail < 0.15** — prompt/style is producing a near-monochrome sprite. Loosen prompt colour constraints or switch to a smaller palette (e.g. `gameboy`/`pico8`).

## Recommendations

Lessons from real runs — read before kicking off a batch.

### Model selection

- **Default to `gpt-image-2`** when deployed in your region (currently `eastus2`-only on Azure). Best silhouette fidelity and palette discipline.
- **`gpt-image-1.5`** is the best broadly-available fallback. Near-parity quality, wider region coverage.
- **`gpt-image-1-mini`** for iteration/drafts: ~3× faster, good enough to validate prompt/style/layout before committing. Weaker at 1-px outlines and small-detail fidelity.
- **Never ask `sora-2` for images** — it's a video model and will fail or waste quota.

### Quality vs size

| Goal                    | Recommended combo                                         |
|-------------------------|-----------------------------------------------------------|
| Final 32×32 sprite      | `--size 32 --quality medium`, rely on `--outline palette-darkest` |
| Final 64×64 sprite      | `--size 64 --quality medium` or `high`                    |
| Tileset (32-px tiles)   | `--tile-size 32 --quality medium` + `--seamless auto`     |
| Walk cycle              | `--tile-size 32 --quality medium` — frame 0 dictates everything; invest quality there |
| Iteration / A-B prompts | `--size 32 --quality low --deployment gpt-image-1-mini`   |

`--quality low` at 32 px is fine for shape testing but will soft-fail outline/coverage QA. Don't chase hard gates at `low`.

### Palette strategy

- When in doubt, use `--palette auto` and trust the keyword table.
- `db32` is the default safe choice: covers earth/foliage/water/metal.
- `pico8` over-saturates dungeons, armour, and stone — its auto-pick rules already steer those to `db32`, don't override.
- For animation consistency, **pass the same palette to all frames**. Gemini frame-to-frame drift is absorbed by the palette quantize step.

### Animation-specific

- Frame 0 is generated by `gpt-image-2` / Azure. Frames 1..N are Gemini with frame 0 as reference. Spend your prompt-engineering budget on frame 0.
- `walk` with 4 frames is the sweet spot. 2 frames looks janky; 8 frames rarely improves perceived motion and 4× the Gemini cost.
- `--transparent-bg` uses a *shared* bbox across all frames — do not post-process frames individually or they will jitter.
- Expect to reroll ~1-in-4 animations. Budget for it.

### Cost / rate

- Fresh Azure image deployments default to **capacity 1 ≈ 1 req/60s**. For batch generation (e.g. 16-tile tileset), either bump capacity (PATCH `sku.capacity`) or run sequentially with retry.
- OpenAI direct has no per-deployment cap but is priced per-image; `low` quality is roughly 1/4 the cost of `high`.
- `rembg` (on `--transparent-bg`) is local CPU — free but slow (~2-4 s/image on first call, cached after).

### QA-driven iteration loop

1. First pass: `--quality low`, no `--qa` — just eyeball shape and pose.
2. Second pass: `--quality medium --qa`. Read `.qa.json`. If all hard gates pass, ship.
3. On soft fails:
   - `outline_coverage` → already handled by `--outline palette-darkest` default; only worry if you set `--outline none`.
   - `palette_coverage` low → richer prompt or smaller palette.
   - `palette_coverage` high → subject is too busy for the palette; scale down palette or simplify prompt.
4. On hard fails, don't tune — regenerate with a different seed/prompt. Hard-fail metrics (palette fidelity, alpha crispness, silhouette IoU) are binary problems, not degrees.

### Path / install

Scripts in this doc are shown under `~/.claude/skills/ai-pixel-art-image-generation/` but the skill is agent-agnostic. Substitute your install root:

- Claude Code: `~/.claude/skills/ai-pixel-art-image-generation/`
- OpenCode: `~/.config/opencode/skill/ai-pixel-art-image-generation/`
- Cloned repo / dev: run from the repo root with `python scripts/…`

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
