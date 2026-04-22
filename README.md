# foundry-image-gen

A [Claude Code skill](https://docs.claude.com/en/docs/claude-code/skills) for generating images via **Microsoft Azure AI Foundry**, with an integrated pipeline for producing Tiled-compatible pixel-art sprites, tilesets, and sprite-sheet animations for 2D games.

## Examples

All generated end-to-end from a text prompt by this skill. All previews are nearest-neighbor upscaled so the pixel grid stays visible on GitHub; originals are alongside in [`assets/examples/`](assets/examples/).

### Sprites (128×128, shown at 4× = 512×512)

| Cat wizard (`aap64`) | Knight with sword and shield (`db32`) |
|:---:|:---:|
| <img src="assets/examples/sprite_cat_wizard_preview.png" width="320" alt="orange tabby cat wizard sprite"> | <img src="assets/examples/sprite_knight_preview.png" width="320" alt="pixel art knight sprite"> |
| `--palette aap64 --outline palette-darkest --transparent-bg` | `--palette db32 --outline palette-darkest --transparent-bg` |

### Seamless tileset (4 tiles, 32×32 each, `db32` palette via `--palette auto`)

<img src="assets/examples/tileset_overworld_preview.png" width="320" alt="seamless overworld tileset: grass, dirt, cobblestone, water">

Each tile passes the hard `tile_seam_diff_mean` gate — drop it into Tiled, paint a map, and boundaries disappear. TSX and TMJ export are next to the PNG.

### Walk-cycle animation (4 frames, 64×64 each, `db32`, 150 ms/frame)

| Animated GIF | Source sheet (4 frames, nearest-neighbor upscaled) |
|:---:|:---:|
| <img src="assets/examples/animation_knight/knight_walk.gif" width="256" alt="knight walk cycle"> | <img src="assets/examples/animation_knight_sheet_preview.png" width="512" alt="knight walk sheet 4 frames"> |

Frame 0 comes from Azure `gpt-image-1.5`; frames 1–3 come from Gemini 2.5 Flash Image with frame 0 as a reference. The QA report reports `silhouette_iou_f0_f2 = 0.99`, `bbox_drift_x = 0`, `bbox_drift_y = 1` (the expected 1 px vertical bob on passing frames).

## What it does

Two user-facing modes:

1. **General image generation** — text-to-image via `gpt-image-1.5` on Azure Foundry.
2. **Pixel-art game-asset mode** — Azure generation + nearest-neighbor downscale + named-palette quantize + (for animations) Gemini 2.5 Flash Image reference-based frame consistency + TSX/TMJ export for [Tiled](https://www.mapeditor.org/).

The skill ships deterministic QA metrics for every pipeline, with hard gates on palette fidelity, alpha crispness, tile seam continuity, and walk-cycle alignment.

## Scripts

| Script | Purpose |
|---|---|
| `scripts/generate_image.py` | General-purpose image (any subject, any 1024/1536 size). |
| `scripts/generate_sprite.py` | Single pixel-art sprite with outline and named palette. |
| `scripts/generate_tileset.py` | N unique seamless tiles packed into a sheet + TSX + TMJ. |
| `scripts/generate_animation.py` | 2–8 frame sprite-sheet animation + TSX `<animation>` block. |
| `scripts/pixelize.py` | Post-process an existing image into pixel art. |
| `scripts/qa_report.py` | Standalone QA metrics on an existing pixel-art PNG. |

## Install

```bash
pip install openai azure-identity google-genai pillow rembg onnxruntime
```

## Configure

Set these before running:

```bash
export AZURE_OPENAI_ENDPOINT="https://<your-foundry-resource>.cognitiveservices.azure.com/"
export GEMINI_API_KEY="<your-gemini-api-key>"   # only needed for generate_animation.py
```

Azure auth order: Azure CLI (`az login`) → `DefaultAzureCredential` → `AZURE_OPENAI_API_KEY`. No endpoint or subscription IDs are baked into the code.

## Examples

Sprite:

```bash
python3 scripts/generate_sprite.py \
  --prompt "orange tabby cat, front view, idle" \
  --size 64 --palette auto --transparent-bg --outline palette-darkest --qa \
  --output out/cat.png
```

Seamless tileset:

```bash
python3 scripts/generate_tileset.py \
  --prompt "grass, dirt, stone, water" \
  --tile-size 32 --count 4 --columns 2 --palette auto \
  --seamless auto --name overworld --output-dir out/overworld/ --qa
```

Walk-cycle animation:

```bash
python3 scripts/generate_animation.py \
  --prompt "knight walking right" --frames 4 --tile-size 32 \
  --palette db16 --action walk --transparent-bg \
  --name knight_walk --output-dir out/knight/ --qa
```

See `SKILL.md` for the full reference and `references/` for prompt-engineering, Tiled format, and palette details.

## Install as a Claude Code skill

Clone into your `~/.claude/skills/` directory:

```bash
git clone https://github.com/ianlintner/foundry-image-gen.git ~/.claude/skills/foundry-image-gen
```

Claude Code auto-discovers the skill via `SKILL.md`.

### Quickstart prompt for Claude Code

Paste this into a fresh Claude Code session and it will install the skill and walk you through credential setup interactively:

> Install the `foundry-image-gen` skill from https://github.com/ianlintner/foundry-image-gen into `~/.claude/skills/foundry-image-gen`, install its Python dependencies, then ask me where my Azure Foundry endpoint and Gemini API key should go. Don't assume — check which auth path I'm using (`az login`, `DefaultAzureCredential`, or a static `AZURE_OPENAI_API_KEY`), tell me which shell rc file to export the env vars in, and verify the install by generating a small sprite with `--qa`.

## License

MIT. See `LICENSE`.
