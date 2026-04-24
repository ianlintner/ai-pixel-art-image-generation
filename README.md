# AI Pixel Art & Tile Map Generator

A game developer toolkit for AI-generated pixel art, tile maps, sprite-sheet animations, and other game graphic assets — packaged as a [Claude Code skill](https://docs.claude.com/en/docs/claude-code/skills) on top of **OpenAI or Azure AI Foundry** (`gpt-image-2`) and **Google Gemini 2.5 Flash Image**. Outputs are Tiled-compatible (TSX/TMJ) so sprites and tilesets drop straight into your map editor.

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

Frame 0 comes from OpenAI/Azure `gpt-image-2`; frames 1–3 come from Gemini 2.5 Flash Image with frame 0 as a reference. The QA report reports `silhouette_iou_f0_f2 = 0.99`, `bbox_drift_x = 0`, `bbox_drift_y = 1` (the expected 1 px vertical bob on passing frames).

## Quickstart (Claude Code)

Paste this prompt into a fresh Claude Code session. It clones the skill, installs the Python dependencies, and walks you through credential setup interactively.

> Install the `ai-pixel-art-image-generation` skill from https://github.com/ianlintner/ai-pixel-art-image-generation into `~/.claude/skills/ai-pixel-art-image-generation`, install its Python dependencies, then ask whether I want direct OpenAI or Azure AI Foundry for `gpt-image-2`, and ask for the Gemini API key if I want animations. Don't assume — check which auth path I'm using (`OPENAI_API_KEY`, `az login`, `DefaultAzureCredential`, or a static `AZURE_OPENAI_API_KEY`), tell me which shell rc file to export the env vars in, and verify the install by generating a small sprite with `--qa`.

Once the skill is installed, Claude Code auto-discovers it via `SKILL.md` and you can ask things like "generate a 64px pixel-art knight sprite" or "make me a seamless grass-and-stone tileset for my overworld map."

## What it does

Two user-facing modes:

1. **General image generation** — text-to-image via `gpt-image-2` on OpenAI/Azure.
2. **Pixel-art game-asset mode** — OpenAI/Azure generation + nearest-neighbor downscale + named-palette quantize + (for animations) Gemini 2.5 Flash Image reference-based frame consistency + TSX/TMJ export for [Tiled](https://www.mapeditor.org/).

The skill ships deterministic QA metrics for every pipeline, with hard gates on palette fidelity, alpha crispness, tile seam continuity, and walk-cycle alignment.

## Scripts

| Script | Purpose |
|---|---|
| `scripts/generate_image.py` | General-purpose image (any subject, fixed or flexible `gpt-image-2` size). |
| `scripts/generate_sprite.py` | Single pixel-art sprite with outline, named palette, and `--variants`/`--style` variation. |
| `scripts/generate_tileset.py` | N unique seamless tiles packed into a sheet + TSX + TMJ. `--variants` generates multiple coherent tilesets. |
| `scripts/generate_animation.py` | 2–8 frame sprite-sheet animation + TSX `<animation>` block. `--variants` generates multiple full walk cycles. |
| `scripts/pixelize.py` | Post-process an existing image into pixel art. |
| `scripts/qa_report.py` | Standalone QA metrics on an existing pixel-art PNG. |

## Manual install

If you prefer to install without the Claude Code quickstart prompt:

```bash
git clone https://github.com/ianlintner/ai-pixel-art-image-generation.git ~/.claude/skills/ai-pixel-art-image-generation
pip install openai azure-identity google-genai pillow rembg onnxruntime
```

## Configure

For direct OpenAI, set:

```bash
export OPENAI_API_KEY="<your-openai-api-key>"
```

For Azure AI Foundry, set:

```bash
export AZURE_OPENAI_ENDPOINT="https://<your-foundry-resource>.cognitiveservices.azure.com/"
```

For animations, also set:

```bash
export GEMINI_API_KEY="<your-gemini-api-key>"
```

Provider selection is `auto`: Azure is used when `AZURE_OPENAI_ENDPOINT` is set, otherwise direct OpenAI is used. Override with `--provider openai` or `--provider azure`. Azure auth order: Azure CLI (`az login`) → `DefaultAzureCredential` → `AZURE_OPENAI_API_KEY`.

## CLI examples

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

## Variation controls (fighting samey outputs)

`gpt-image-2` does not expose a `temperature` or `seed` parameter, so identical
prompts converge on near-identical outputs. To keep a body of generated assets
from looking same-y, all three generators accept variation flags that rotate
**stylistic** clauses in the prompt suffix while keeping load-bearing
constraints (`pixel art`, `limited palette`, `no text`, `no borders`) intact.

| Flag | What it does |
|---|---|
| `--variants N` (alias `--n N`) | Generate N outputs. Sprites: `out_01.png…out_NN.png`. Tilesets/animations: N complete sets in numbered subdirs. |
| `--style <preset>` | One of `chibi`, `hi-bit-snes`, `gb-4color`, `mega-drive`, `modern-indie`, `nes`. Biases axis pools, palette hint, outline default. |
| `--style-seed <str>` | Override RNG seed for style sampling. Default: `prompt + variant index`. Same seed → same style. |
| `--rewrite-prompts` | Per-variant, call `gpt-4.1-mini` to rephrase the subject (mood / pose / silhouette emphasis only). Closest analog to image-model "temperature". Falls back silently if the text model is unavailable. |
| `--outline-mode {palette-darkest,tone-shift,none,random}` | `tone-shift` is the softer SNES "selout" look; `random` varies between `palette-darkest` and `tone-shift` per variant. |
| `--palette-jitter 0..1` | Per-variant hue/lightness shift on the chosen palette. `0.05` is gentle; `0.15` is bold. Anchor black/white are preserved. |
| `--palette auto` | Now picks a seeded palette from the compatible-candidate list per variant. Same seed → same palette; different variants → different palettes. |

Every generated file now writes a `.gen.json` sidecar next to the output with
the exact final prompt, palette, style axes, preset, provider/model, and
variant seed — reproducibility even though the image API has no seed.

Examples:

```bash
# 4 sprite variants of the same cat, different moods / lighting / angles
python3 scripts/generate_sprite.py \
  --prompt "orange tabby cat, front view, idle" \
  --size 64 --palette auto --transparent-bg \
  --variants 4 --palette-jitter 0.05 --outline-mode random \
  --output out/cats/cat.png

# 3 complete SNES-styled overworld tilesets
python3 scripts/generate_tileset.py \
  --prompt "grass, dirt, stone, water" \
  --tile-size 32 --count 4 --columns 2 --palette auto \
  --variants 3 --style hi-bit-snes \
  --name overworld --output-dir out/overworld/

# 3 knight walk cycles with rewritten subject prompts
python3 scripts/generate_animation.py \
  --prompt "knight walking right" --frames 4 --tile-size 32 \
  --palette auto --action walk --transparent-bg \
  --variants 3 --style modern-indie --rewrite-prompts \
  --name knight_walk --output-dir out/knight/
```

Design notes:
- **Tilesets** sample style **once per set** (not per tile) so every tile in a
  given set is stylistically coherent.
- **Animations** sample style **once per set** and apply it to the *base frame
  only*. Gemini then locks the look across frames via the reference image;
  per-frame style randomization would break silhouette/palette consistency.
- `--rewrite-prompts` always uses the original prompt verbatim for variant 0,
  so at least one output matches your exact wording.

See `SKILL.md` for the full reference and `references/` for prompt-engineering, Tiled format, and palette details.

## License

MIT. See `LICENSE`.
