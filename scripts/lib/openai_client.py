"""Direct OpenAI image generation client wrapper."""

from __future__ import annotations

import os
import sys

DEFAULT_MODEL = "gpt-image-2"


def build_client(api_key: str | None = None, organization: str | None = None):
    try:
        from openai import OpenAI
    except ImportError:
        print(
            "ERROR: openai package not installed. Run: pip install openai",
            file=sys.stderr,
        )
        sys.exit(1)

    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print(
            "ERROR: OpenAI provider requires OPENAI_API_KEY or --openai-api-key.",
            file=sys.stderr,
        )
        sys.exit(1)

    return OpenAI(
        api_key=api_key,
        organization=organization or os.environ.get("OPENAI_ORG_ID"),
    )


def resolve_model(cli_value: str | None = None) -> str:
    return cli_value or os.environ.get("OPENAI_IMAGE_MODEL", DEFAULT_MODEL)


def generate_image_bytes(
    client,
    *,
    model: str,
    prompt: str,
    size: str = "1024x1024",
    quality: str = "high",
    n: int = 1,
) -> list[bytes]:
    """Generate images and return a list of raw image bytes."""
    import base64
    import urllib.request

    response = client.images.generate(
        model=model,
        prompt=prompt,
        size=size,
        quality=quality,
        n=n,
    )

    out: list[bytes] = []
    for img in response.data:
        if getattr(img, "b64_json", None):
            out.append(base64.b64decode(img.b64_json))
        elif getattr(img, "url", None):
            with urllib.request.urlopen(img.url) as r:
                out.append(r.read())
        else:
            raise RuntimeError(f"No image data in response item: {img}")
    return out
