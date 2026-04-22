# Install

## Quickstart: let Claude Code do it

Paste this prompt into a fresh Claude Code session. It clones the skill, installs the Python dependencies, and walks through credential setup interactively — Claude Code will ask where your Azure Foundry endpoint lives and which auth path you're using before writing anything.

> Install the `ai-pixel-art-image-generator` skill from https://github.com/ianlintner/ai-pixel-art-image-generator into `~/.claude/skills/ai-pixel-art-image-generator`, install its Python dependencies, then ask me where my Azure Foundry endpoint and Gemini API key should go. Don't assume — check which auth path I'm using (`az login`, `DefaultAzureCredential`, or a static `AZURE_OPENAI_API_KEY`), tell me which shell rc file to export the env vars in, and verify the install by generating a small sprite with `--qa`.

The manual steps below cover the same ground if you prefer to run them yourself.

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
git clone https://github.com/ianlintner/ai-pixel-art-image-generator.git ~/.claude/skills/ai-pixel-art-image-generator
```

## Verify the install

Generate a small sprite and inspect the QA report:

```bash
python3 ~/.claude/skills/ai-pixel-art-image-generator/scripts/generate_sprite.py \
  --prompt "orange tabby cat, front view, idle" \
  --size 64 --palette auto --transparent-bg --outline palette-darkest --qa \
  --output /tmp/cat.png
```

Expected output ends with a QA table where every **hard** gate is `PASS`.
