# foundry-image-gen

A [Claude Code skill](https://docs.claude.com/en/docs/claude-code/skills) for generating images via **Microsoft Azure AI Foundry**, with an integrated pipeline for producing Tiled-compatible pixel-art sprites, tilesets, and sprite-sheet animations for 2D games.

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
git clone https://github.com/<you>/foundry-image-gen.git ~/.claude/skills/foundry-image-gen
```

Claude Code auto-discovers the skill via `SKILL.md`.

## License

MIT. See `LICENSE`.
