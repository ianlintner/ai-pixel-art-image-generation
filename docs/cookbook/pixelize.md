# Recipe: pixelize an existing image

Post-process any PNG — a photo, an AI-generated illustration, concept art — into a palette-quantized pixel sprite. No new generation needed.

## Command

```bash
python3 scripts/pixelize.py \
  --input /tmp/raw_illustration.png \
  --output /tmp/pixelized.png \
  --size 64 --palette db32 \
  --transparent-bg --outline palette-darkest
```

## Flags explained

| Flag | Meaning |
|---|---|
| `--input` | Path to the source image (any size, any format Pillow can open). |
| `--size N` | Target square side, in pixels. The script Lanczos-downscales to `2N × 2N`, then nearest-neighbor to `N × N` so the grid stays crisp. |
| `--palette NAME` | Named palette for quantize (see [Palettes](../reference/palettes.md)). |
| `--transparent-bg` | Runs `rembg` (u2net) to cut out the subject, then tight-crops so it fills the frame. |
| `--outline palette-darkest` | Adds a 1-px dark ring around the silhouette using the darkest neighbouring palette color. |

## Pipeline steps

1. Load source image as RGBA.
2. (Optional) `rembg` background removal + tight-crop to alpha bbox.
3. Two-stage downscale: Lanczos to `2× target`, then nearest-neighbor to `target`.
4. (Optional) 1-px outline pass before palette quantize so outline colors participate in the quantize step.
5. Palette quantize against the named palette (`PIL.Image.quantize` with `Dither.NONE`).
6. Alpha threshold binarization at 128 so edges stay hard.
7. Save RGBA PNG.

## When to use this

- You have a non-pixel source (photo, AI illustration, hand-drawn concept) and want it to match your game's pixel-art style.
- You're iterating on the palette of an existing sprite — pixelize again with a different `--palette`.
- You want to regenerate a known sprite at a different size without re-prompting Azure.
