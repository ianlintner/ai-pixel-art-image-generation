# Install

## Python dependencies

```bash
pip install openai azure-identity google-genai pillow rembg onnxruntime
```

`rembg` downloads a `u2net` ONNX model on first run (~170 MB); cache it with `REMBG_MODEL_DIR` if you need to pin the location.

## Environment variables

```bash
export AZURE_OPENAI_ENDPOINT="https://<your-foundry-resource>.cognitiveservices.azure.com/"
# Only needed for generate_animation.py (frames 2..N use Gemini).
export GEMINI_API_KEY="<your-gemini-api-key>"
```

## Azure authentication

The scripts resolve credentials in this order:

1. **Azure CLI** — run `az login` once; token cache is reused.
2. **`DefaultAzureCredential`** — picks up managed identity, environment vars, or VS Code sign-in.
3. **`AZURE_OPENAI_API_KEY`** — static key, last resort.

No endpoint or subscription IDs are baked into the scripts.

## Install as a Claude Code skill

Clone into your `~/.claude/skills/` directory so Claude Code auto-discovers it via `SKILL.md`:

```bash
git clone https://github.com/ianlintner/foundry-image-gen.git ~/.claude/skills/foundry-image-gen
```

## Verify the install

Generate a small sprite and inspect the QA report:

```bash
python3 ~/.claude/skills/foundry-image-gen/scripts/generate_sprite.py \
  --prompt "orange tabby cat, front view, idle" \
  --size 64 --palette auto --transparent-bg --outline palette-darkest --qa \
  --output /tmp/cat.png
```

Expected output ends with a QA table where every **hard** gate is `PASS`.
