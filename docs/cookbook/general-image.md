# Recipe: general image

Plain text-to-image via Azure Foundry's `gpt-image-1.5`. No pixel-art pipeline, no palette quantize — just a PNG.

## Command

```bash
python3 scripts/generate_image.py \
  --prompt "a misty mountain valley at dawn, oil painting" \
  --size 1024x1024 --quality high \
  --output /tmp/valley.png
```

## Flags explained

| Flag | Meaning |
|---|---|
| `--size` | `1024x1024`, `1536x1024`, or `1024x1536`. |
| `--quality` | `low` / `medium` / `high`. Higher quality costs more tokens and takes longer. |
| `--deployment NAME` | Override the default `gpt-image-1.5` deployment name. |
| `--output` | Path to write the PNG. Parent directories are created. |

## When to use this instead of the pixel-art scripts

- Non-game art — illustrations, concept art, reference imagery.
- Source material to feed into `pixelize.py` later.
- Any time you need a raw generation without the rembg / palette-quantize / outline pipeline.

## Tips

- For landscape / portrait aspect ratios, use `1536x1024` or `1024x1536`. The skill does not currently support arbitrary aspect ratios.
- Long prompts benefit from explicit style anchors (e.g. `oil painting`, `photograph`, `anime screencap`). The model follows stylistic keywords more reliably than mood words.
- Feed the raw output into the [Pixelize existing](pixelize.md) recipe to convert it to pixel art after the fact.
