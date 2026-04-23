#!/usr/bin/env python3
"""
Image generator for OpenAI or Azure AI Foundry.

Azure auth priority:
  1. Azure CLI credential (az login) — for local/interactive use
  2. DefaultAzureCredential — covers managed identity, env SP, workload identity
  3. API key fallback — for headless/CI via AZURE_OPENAI_API_KEY or --api-key

Environment variables:
  IMAGE_PROVIDER           — auto, openai, or azure (default: auto)
  OPENAI_API_KEY           — required for direct OpenAI provider
  OPENAI_IMAGE_MODEL       — default: gpt-image-2
  AZURE_OPENAI_ENDPOINT    — required (e.g. https://my-resource.openai.azure.com/)
  AZURE_OPENAI_API_KEY     — fallback API key (headless/CI)
  AZURE_OPENAI_API_VERSION — default: 2025-04-01-preview
  AZURE_IMAGE_DEPLOYMENT   — default: gpt-image-2

Usage:
  python3 generate_image.py --prompt "a cat on mars" --output ~/cat.png
  python3 generate_image.py --provider openai --prompt "..." --model gpt-image-2 --output ~/img.png
"""

import argparse
import sys
from pathlib import Path

# Allow running as a script from inside scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.image_client import VALID_PROVIDERS, build_image_generator, generate_image_bytes
from lib.image_options import DEFAULT_IMAGE_SIZE, POPULAR_IMAGE_SIZES, validate_image_size


def parse_args():
    p = argparse.ArgumentParser(description="Generate images via OpenAI or Azure AI Foundry")
    p.add_argument("--prompt", required=True, help="Image generation prompt")
    p.add_argument("--output", default="~/generated_image.png", help="Output file path")
    p.add_argument(
        "--size",
        default=DEFAULT_IMAGE_SIZE,
        type=validate_image_size,
        metavar="WIDTHxHEIGHT",
        help=f"Image dimensions; common values: {', '.join(POPULAR_IMAGE_SIZES)}",
    )
    p.add_argument(
        "--quality",
        default="medium",
        choices=["low", "medium", "high"],
        help="Image quality (low/medium/high)",
    )
    p.add_argument("--n", type=int, default=1, help="Number of images (max 1 for gpt-image-1)")
    p.add_argument(
        "--provider", default=None, choices=VALID_PROVIDERS, help="auto, openai, or azure"
    )
    p.add_argument("--endpoint", help="Azure OpenAI endpoint (overrides AZURE_OPENAI_ENDPOINT)")
    p.add_argument("--api-key", dest="api_key", help="Azure API key auth (skips CLI credential)")
    p.add_argument("--openai-api-key", dest="openai_api_key", help="OpenAI API key override")
    p.add_argument("--openai-org", dest="openai_org", help="OpenAI organization override")
    p.add_argument(
        "--deployment",
        default=None,
        help="Image model/deployment override (OpenAI model or Azure deployment)",
    )
    p.add_argument("--model", dest="model", default=None, help=argparse.SUPPRESS)
    p.add_argument(
        "--api-version",
        dest="api_version",
        default=None,
        help="API version (overrides AZURE_OPENAI_API_VERSION)",
    )
    return p.parse_args()


def main():
    args = parse_args()

    model = args.model or args.deployment
    generator = build_image_generator(
        provider=args.provider,
        model=model,
        azure_endpoint=args.endpoint,
        azure_api_key=args.api_key,
        azure_api_version=args.api_version,
        force_azure_api_key=bool(args.api_key),
        openai_api_key=args.openai_api_key,
        openai_organization=args.openai_org,
    )

    print(f"Generating image with {generator.provider}:{generator.model}...")
    print(f"  Prompt: {args.prompt[:80]}{'...' if len(args.prompt) > 80 else ''}")
    print(f"  Size: {args.size}  Quality: {args.quality}")

    try:
        images = generate_image_bytes(
            generator,
            prompt=args.prompt,
            size=args.size,
            quality=args.quality,
            n=args.n,
        )
    except Exception as e:
        print(f"ERROR: Image generation failed: {e}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_bytes(images[0])
    print(f"\nSaved: {output_path}")

    for i, blob in enumerate(images[1:], start=1):
        numbered = output_path.with_stem(f"{output_path.stem}_{i}")
        numbered.write_bytes(blob)
        print(f"Saved: {numbered}")


if __name__ == "__main__":
    main()
