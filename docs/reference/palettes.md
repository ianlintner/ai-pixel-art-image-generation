# Palette Reference

All palettes are implemented in `scripts/lib/palettes.py`. Choose one that fits the target sprite size and intended mood.

## Available Palettes

| Name       | Colors | Vibe                                      | Best at size |
|------------|--------|-------------------------------------------|--------------|
| `gameboy`  | 4      | Classic GameBoy greens, high contrast     | 16, 32       |
| `pico8`    | 16     | PICO-8 fantasy console palette            | 16, 32       |
| `db16`     | 16     | Dawnbringer DB16, warm/broad hues         | 32, 64       |
| `db32`     | 32     | Dawnbringer DB32, strong saturation range | 32, 64       |
| `nes`      | 54     | NES approximation                         | 32, 64       |
| `aap64`    | 64     | Adigun Polack, wide-gamut "AAP-64"        | 64, 128      |

## Pick Guide

- **Going retro-faithful**: `gameboy` for monochrome green nostalgia; `pico8` for bright 80s arcade; `nes` for 8-bit console look.
- **Going modern-indie**: `db16` / `db32` — well-tuned by community, pleasant saturation.
- **Going detailed**: `aap64` — best for larger sprites (64+ px) where you have room for color.

## Palette Color Lists

### GameBoy (4)

```
#0f380f  #306230  #8bac0f  #9bbc0f
```

### PICO-8 (16)

```
#000000  #1d2b53  #7e2553  #008751
#ab5236  #5f574f  #c2c3c7  #fff1e8
#ff004d  #ffa300  #ffec27  #00e436
#29adff  #83769c  #ff77a8  #ffccaa
```

### DB16 (16)

```
#140c1c  #442434  #30346d  #4e4a4e
#854c30  #346524  #d04648  #757161
#597dce  #d27d2c  #8595a1  #6daa2c
#d2aa99  #6dc2ca  #dad45e  #deeed6
```

### DB32 (32)

```
#000000  #222034  #45283c  #663931
#8f563b  #df7126  #d9a066  #eec39a
#fbf236  #99e550  #6abe30  #37946e
#4b692f  #524b24  #323c39  #3f3f74
#306082  #5b6ee1  #639bff  #5fcde4
#cbdbfc  #ffffff  #9badb7  #847e87
#696a6a  #595652  #76428a  #ac3232
#d95763  #d77bba  #8f974a  #8a6f30
```

### NES (54 approx., 64 slots with repeats)

See `scripts/lib/palettes.py` for the full hex list.

### AAP-64 (64)

See `scripts/lib/palettes.py`. Full list by Adigun Polack — strong general-purpose palette for detailed pixel art.

## Why Nearest-Neighbor + Quantize Matters

Diffusion models emit anti-aliased RGB. Direct downscale (Lanczos) keeps sub-pixel AA — pixels won't look "pixel-y". Nearest-neighbor alone still keeps arbitrary colors off the palette. The pipeline combines:

1. Lanczos → 2× target size: preserves detail while reducing AA energy.
2. Nearest-neighbor → target: locks to the pixel grid.
3. `Image.quantize(palette=...)`: snaps every color to the nearest palette entry.
4. Alpha threshold at 128: kills semi-transparent AA edges.

Result: RGBA PNG with exactly the target palette's colors, hard edges, crisp alpha.
