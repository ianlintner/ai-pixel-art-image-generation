# Recipe: sprite-sheet animation

A frame-consistent walk / idle / attack cycle packed into a horizontal sheet, with a Tiled `<animation>` block and a preview GIF.

## What you get

<div class="recipe-preview" markdown>

<figure markdown>
![Knight walk GIF](../examples/animation_knight/knight_walk.gif){ width=256 }
<figcaption>`knight_walk.gif` — 4-frame cycle, 3 fps (built via ffmpeg from the sheet)</figcaption>
</figure>

<figure markdown>
![Knight walk sheet](../examples/animation_knight_sheet_preview.png){ width=512 }
<figcaption>Source sheet — 4 × 64px frames, db32 palette (4× upscale for visibility)</figcaption>
</figure>

</div>

Frame 0 comes from OpenAI/Azure `gpt-image-2`. Frames 1–3 come from Gemini 2.5 Flash Image with **frame 0 as the reference image** (not the previous frame) so drift does not compound. The QA report for this example reads `silhouette_iou_f0_f2 = 0.99`, `bbox_drift_x = 0`, `bbox_drift_y = 1` — the expected 1-px vertical bob on passing frames.

## Command — sprite sheet

```bash
python3 scripts/generate_animation.py \
  --prompt "knight walking right" \
  --frames 4 --tile-size 64 \
  --palette db32 --action walk \
  --transparent-bg \
  --name knight_walk \
  --output-dir assets/examples/animation_knight/ --qa
```

## Command — GIF from sheet

The sheet is 256×64 (4 frames × 64 px). ffmpeg's `untile` splits it; `setpts` is the critical bit — without it ffmpeg assigns all frames the same timestamp and dedupes 3 of them.

```bash
ffmpeg -y -i knight_walk.png \
  -filter_complex "[0:v]untile=4x1,setpts=N/(3*TB),scale=256:256:flags=neighbor,split[a][b];[a]palettegen=reserve_transparent=1[p];[b][p]paletteuse=dither=none:alpha_threshold=128" \
  -r 3 -loop 0 knight_walk.gif
```

- `setpts=N/(3*TB)` gives each frame a distinct timestamp at 3 fps (~333 ms/frame).
- `scale=...:flags=neighbor` upscales nearest-neighbor so the pixel grid survives.
- `paletteuse=dither=none:alpha_threshold=128` preserves hard pixel-art edges through the GIF palette step.

## Flags explained

| Flag | Meaning |
|---|---|
| `--frames 4` | Walk cycles are typically 4 (contact / passing / contact / passing). Idle is usually 2. Attack is usually 4. |
| `--tile-size 64` | Frame side length. 64 gives Gemini enough detail to preserve silhouette; 32 is tighter but silhouette drift is more visible. |
| `--action walk` | Keys into the `POSE_LIBRARY`. `walk`, `idle`, and `attack` ship with explicit per-frame pose descriptors. |
| `--transparent-bg` | Runs `rembg` on every frame, computes the union alpha bbox across all frames, and tight-crops all frames to the same bbox so the silhouette does not drift in the frame. |
| `--qa` | Runs silhouette IoU and bbox drift gates. |

## QA gates checked

- `silhouette_iou_f0_f2 >= 0.85` (hard) — the two contact-pose frames share 85%+ of their alpha mask.
- `bbox_drift_x <= 6` (hard) — walk cycle legs can legitimately extend several px; this gate catches character-size swaps.
- `bbox_drift_y <= 3` (hard) — vertical bob is 1–2 px on passing frames; >3 means the character is falling or rising in-frame.
- `palette_fidelity == 1.0` (hard).

## Tips

- For tighter bob control, use `--action idle` with `--frames 2`.
- If frame 3 drifts badly, reroll with `--frame-seed-offset 3`. Drift tends to compound through Gemini's "same character" interpretation, and reference-to-frame-0 already helps.
- GIF too fast? Lower the fps both in the `setpts=N/(FPS*TB)` expression and the `-r FPS` flag. 3 fps = 333 ms/frame reads cleanly for walks; 2 fps = 500 ms for deliberate / slow cycles.
