# QA Metrics

Every generator script supports `--qa`. The QA pass computes deterministic Pillow-based metrics and writes a `<output>.qa.json` report next to the artifact. Hard-gate failures exit non-zero; soft-gate failures warn to stderr but still exit `0`.

All metric implementations live in [`scripts/lib/qa_metrics.py`](https://github.com/ianlintner/ai-pixel-art-image-generator/blob/main/scripts/lib/qa_metrics.py). Thresholds are declared in the `GATES` dict at the bottom of that file.

## Gate table

| Metric | Scope | Threshold | Type |
|---|---|---|---|
| `palette_fidelity` | all | `== 1.0` | hard |
| `alpha_crispness` | all | `>= 0.999` | hard |
| `tile_seam_diff_mean` | tileset, per tile (wrap) | `< 12.0` on 0–255 L2 scale | hard |
| `baseline_alignment` | sprite | lowest opaque row has ≥3 contiguous opaque px | hard |
| `silhouette_iou_f0_f2` | animation | `>= 0.85` | hard |
| `bbox_drift_x` | animation | `<= 6` px | hard |
| `bbox_drift_y` | animation | `<= 3` px | hard |
| `outline_coverage` | sprite | `>= 0.85` | soft |
| `palette_coverage` | sprite | `0.15 <= x <= 0.60` | soft |

## What each gate catches

**`palette_fidelity`** — after quantize, every opaque RGB must exist in the palette. If it does not, the quantizer ran against the wrong palette or the outline writer failed to snap to palette. Hard-fail because a pixel-art sprite with off-palette colors is not pixel-art.

**`alpha_crispness`** — the fraction of alpha values that are exactly `0` or `255`. Low numbers mean anti-aliased edges leaked through, which produces halo artifacts when the sprite is placed on a background in the target engine.

**`tile_seam_diff_mean`** — mean L2 RGB distance between the left column and right column (and top/bottom rows) of each tile, in 0–255 scale. High numbers mean the tile is not seamless; painting adjacent copies in Tiled shows visible boundary lines. The `edge_match` seamless strategy forces this to `0`.

**`baseline_alignment`** — checks that the sprite has ≥3 contiguous opaque pixels in its lowest opaque row. Catches sprites that float on a single pointy foot or have two disconnected legs.

**`silhouette_iou_f0_f2`** — intersection-over-union between the alpha masks of frames 0 and 2 of a walk cycle. Walk cycles use two contact poses (mirrored), so their silhouettes should match at ~99%. Drift below 85% means Gemini produced a different character.

**`bbox_drift_x` / `bbox_drift_y`** — max per-axis drift of the alpha bbox across all frames, relative to frame 0. The x-axis gate is lax (≤6) because walk cycles legitimately extend legs several px. The y-axis gate is tight (≤3) because vertical bob should be 1–2 px — more than that means the character is falling or rising in frame.

**`outline_coverage`** *(soft)* — fraction of silhouette-boundary pixels that land in the darkest quartile of the palette (luminance). Below 0.85 means the `--outline palette-darkest` pass did not produce a consistent dark ring.

**`palette_coverage`** *(soft)* — unique opaque colors divided by palette size. Both tails are warnings: `< 0.15` means the sprite uses 2–3 colors only (probably flat-coloured), `> 0.60` means it grabs most palette entries (visual noise). These are defaults tuned for 64×64 sprites; at 128×128 both tails are looser in practice.

## Running QA standalone

Use `scripts/qa_report.py` to re-run metrics against an existing PNG without regenerating:

```bash
python3 scripts/qa_report.py \
  --input assets/examples/tileset_overworld/overworld.png \
  --kind tileset --palette db32 \
  --tile-size 32 --columns 2
```

The CI workflow [`ci.yml`](https://github.com/ianlintner/ai-pixel-art-image-generator/blob/main/.github/workflows/ci.yml) runs this on every bundled example artifact so the committed examples are guaranteed to pass.
