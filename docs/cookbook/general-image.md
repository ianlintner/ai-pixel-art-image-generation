# Recipe: general image

Plain text-to-image via OpenAI/Azure's `gpt-image-2`. No pixel-art pipeline, no palette quantize — just a PNG.

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
| `--size` | Common values include `1024x1024`, `1536x1024`, `1024x1536`, `2048x2048`, `2048x1152`, `3840x2160`, `2160x3840`, or `auto`. |
| `--quality` | `low` / `medium` / `high`. Higher quality costs more tokens and takes longer. |
| `--provider` | `auto`, `openai`, or `azure`. |
| `--deployment NAME` | Override the default `gpt-image-2` model/deployment name. |
| `--output` | Path to write the PNG. Parent directories are created. |

## When to use this instead of the pixel-art scripts

- Non-game art — illustrations, concept art, reference imagery.
- Source material to feed into `pixelize.py` later.
- Any time you need a raw generation without the rembg / palette-quantize / outline pipeline.

## Tips

- For custom sizes, use dimensions that are multiples of 16, no more than 3840 px on either edge, within a 3:1 aspect ratio, and between 655,360 and 8,294,400 total pixels.
- Long prompts benefit from explicit style anchors (e.g. `oil painting`, `photograph`, `anime screencap`). The model follows stylistic keywords more reliably than mood words.
- Feed the raw output into the [Pixelize existing](pixelize.md) recipe to convert it to pixel art after the fact.
