# Pixel Art Prompting Guide

Generative image models do not emit true grid-aligned pixel art. They produce rasterized "pixel-art-styled" images that require a downscale + palette-quantize post-process to become real pixel art. This guide lists prompt patterns that minimize artifacts in the source image and therefore produce cleaner output after pixelization.

## Prompt Structure

Pattern:

```
{subject}, {view angle}, {pose/action},
{style qualifier}, {background constraint},
{negative constraints}
```

### Recommended building blocks

- **Style qualifier**: "pixel art sprite", "flat pixel art", "16-bit RPG sprite", "retro console style"
- **View angles**: "side view, profile", "top-down view", "3/4 isometric view", "front view"
- **Background constraints**: "plain flat background", "solid magenta background" (helps `rembg`), "transparent background"
- **Negatives that matter**: "no text, no watermark, no logo", "no anti-aliasing", "hard edges", "no gradients"

### Strong prompt example

```
orange tabby cat, front view, idle standing pose.
Pixel art sprite, clean hard edges, limited palette,
plain flat background, no text, no watermark, no anti-aliasing.
```

### Weak prompt example (produces mush)

```
cute cat pixel art
```

The model has too much latitude. Expect smudgy anti-aliasing and drifting palette.

## Size and Palette Choices

Recommended target sizes:

| Target | Use case                      | Palette suggestion        |
|--------|-------------------------------|---------------------------|
| 16     | Tiny sprites, item icons      | `pico8`, `gameboy`        |
| 32     | Standard top-down sprites     | `db16`, `db32`            |
| 64     | Detailed hero sprites         | `db32`, `aap64`           |
| 128    | Portraits, high-detail props  | `aap64`                   |

Rule of thumb: richer palettes (`aap64`) work on bigger sizes because you have more pixels to spread the colors across. `gameboy` (4 colors) only looks intentional at 16–32 px.

## Tileset-Specific Prompts

Tiles need to look seamless. Extra constraints:

- "top-down game tile, seamless, centered"
- "single tile, no border, no frame, no UI chrome"
- "tileable edges" (soft ask — models don't truly tile)

For distinct tile types in one set, pass them comma-separated to `generate_tileset.py --prompt`:

```
grass, dirt, stone, water, sand, path, wood plank, stone brick
```

Each becomes its own API call. The script expands/repeats names if fewer than `--count`.

## Animation-Specific Prompts

Frame 0 (via Azure) sets the authoritative silhouette. Keep this prompt simple and canonical:

```
knight with blue cape, side view profile, standing still
```

Frames 1..N (via Gemini with frame 0 as reference) are driven automatically by:

```
Same character as the reference image, exact same palette and silhouette.
{action} animation, frame {N} of {total}.
```

### Reroll strategy

Diffusion models drift. For a 4-frame walk cycle, expect ~1 frame to need a reroll. Run the command again or re-run with a tweaked action verb ("walking step left foot forward", "walking step right foot forward") for more deterministic framing.

## Things to Avoid in Prompts

- "photorealistic" — fights the pixel-art style
- "smooth shading" / "gradients" — adds AA the quantizer has to fight
- Real-person names — Azure content filter will reject
- Copyrighted character names (Mario, Pikachu, etc.) — rejected and counterproductive

## When to Retry vs. When to Hand-Fix in Aseprite

- Silhouette is wrong → retry with tighter view-angle prompt
- Palette leaks a single muddy color → retry, or add palette name to prompt ("PICO-8 palette")
- One pixel out of place → fix in Aseprite; not worth the API call
- Animation breaks between frames 1 and 2 → reroll frame 2 only (re-run with different seed / prompt wording)
