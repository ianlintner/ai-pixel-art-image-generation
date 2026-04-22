#!/usr/bin/env python3
"""
Azure AI Foundry Image Generator

Auth priority:
  1. Azure CLI credential (az login) — for local/interactive use
  2. DefaultAzureCredential — covers managed identity, env SP, workload identity
  3. API key fallback — for headless/CI via AZURE_OPENAI_API_KEY or --api-key

Environment variables:
  AZURE_OPENAI_ENDPOINT    — required (e.g. https://my-resource.openai.azure.com/)
  AZURE_OPENAI_API_KEY     — fallback API key (headless/CI)
  AZURE_OPENAI_API_VERSION — default: 2025-04-01-preview
  AZURE_IMAGE_DEPLOYMENT   — default: gpt-image-1.5

Usage:
  python3 generate_image.py --prompt "a cat on mars" --output ~/cat.png
  python3 generate_image.py --prompt "..." --deployment gpt-image-1-mini --output ~/fast.png
"""

import argparse
import os
import sys
from pathlib import Path

# Allow running as a script from inside scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.azure_client import build_client, generate_image_bytes, resolve_deployment


VALID_SIZES = ["1024x1024", "1536x1024", "1024x1536", "auto"]


def parse_args():
    p = argparse.ArgumentParser(description="Generate images via Azure AI Foundry")
    p.add_argument("--prompt", required=True, help="Image generation prompt")
    p.add_argument("--output", default="~/generated_image.png", help="Output file path")
    p.add_argument("--size", default="1024x1024", choices=VALID_SIZES,
                   help="Image dimensions")
    p.add_argument("--quality", default="medium", choices=["low", "medium", "high"],
                   help="Image quality (low/medium/high)")
    p.add_argument("--n", type=int, default=1, help="Number of images (max 1 for gpt-image-1)")
    p.add_argument("--endpoint", help="Azure OpenAI endpoint (overrides AZURE_OPENAI_ENDPOINT)")
    p.add_argument("--api-key", dest="api_key", help="Force API key auth (skips CLI credential)")
    p.add_argument("--deployment", default=None, help="Deployment name (overrides AZURE_IMAGE_DEPLOYMENT)")
    p.add_argument("--api-version", dest="api_version", default=None,
                   help="API version (overrides AZURE_OPENAI_API_VERSION)")
    return p.parse_args()


def main():
    args = parse_args()

    deployment = resolve_deployment(args.deployment)
    client = build_client(
        endpoint=args.endpoint,
        api_key=args.api_key,
        api_version=args.api_version,
        force_api_key=bool(args.api_key),
    )

    print(f"Generating image with {deployment}...")
    print(f"  Prompt: {args.prompt[:80]}{'...' if len(args.prompt) > 80 else ''}")
    print(f"  Size: {args.size}  Quality: {args.quality}")

    try:
        images = generate_image_bytes(
            client,
            deployment=deployment,
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
