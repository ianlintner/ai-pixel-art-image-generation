# Recipe: single sprite

A single pixel-art character with a transparent background, a deliberate 1-px outline, and colors snapped to a named palette.

## What you get

<div class="recipe-preview" markdown>

<figure markdown>
![Cat wizard 128×128](../examples/sprite_cat_wizard_preview.png){ width=320 }
<figcaption>`sprite_cat_wizard_128.png` — 128×128, aap64 palette (shown at 4× for visibility)</figcaption>
</figure>

<figure markdown>
![Knight 128×128](../examples/sprite_knight_preview.png){ width=320 }
<figcaption>`sprite_knight_128.png` — 128×128, db32 palette (shown at 4× for visibility)</figcaption>
</figure>

</div>

## Command

=== "Cat wizard"

    ```bash
    python3 scripts/generate_sprite.py \
      --prompt "orange tabby cat wizard in a purple robe holding a wooden staff" \
      --size 128 --palette aap64 --transparent-bg \
      --outline palette-darkest --qa \
      --output assets/examples/sprite_cat_wizard_128.png
    ```

=== "Knight"

    ```bash
    python3 scripts/generate_sprite.py \
      --prompt "pixel art knight with sword and shield, side view" \
      --size 128 --palette db32 --transparent-bg \
      --outline palette-darkest --qa \
      --output assets/examples/sprite_knight_128.png
    ```

## Flags explained

| Flag | Meaning |
|---|---|
| `--size 128` | Final square side in pixels. Pipeline Lanczos-downscales to 256 then nearest-neighbor-downscales to 128 so the grid stays crisp. |
| `--palette aap64` | Named palette (see [Palettes](../reference/palettes.md)). Use `auto` to pick by subject keyword. |
| `--transparent-bg` | Runs `rembg` to cut out the subject and tight-crops the result so the sprite fills the frame edge-to-edge. |
| `--outline palette-darkest` | Adds a 1-px dark ring around the silhouette. The outline color is picked from each outline pixel's darkest opaque 8-neighbor so it participates in quantize and stays in-palette. |
| `--qa` | Runs the QA gates and writes a `<output>.qa.json` report. Hard-fail → non-zero exit. |

## QA gates checked

- `palette_fidelity == 1.0` (hard) — every opaque pixel is exactly a palette color.
- `alpha_crispness >= 0.999` (hard) — alpha is ~entirely 0 or 255.
- `baseline_alignment` (hard) — lowest opaque row has ≥3 contiguous opaque pixels, so the sprite stands on something.
- `outline_coverage >= 0.85` (soft) — silhouette boundary is in the darkest quartile of the palette.
- `palette_coverage` (soft) — warns at both tails to catch "all one color" or "every palette entry used" defects.

## Tips

- For a tighter palette, pass `--palette auto` and let the keyword matcher pick (e.g. `stone` → `db32`, `tropical` → `aap64`).
- Drop the `--outline` flag for pre-rendered or painterly looks.
- For 64×64 sprites, the `baseline_alignment` gate matters most — without it you'll get a floating character.
