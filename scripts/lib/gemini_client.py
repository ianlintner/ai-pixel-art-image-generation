"""Google Gemini 2.5 Flash Image client wrapper.

Gemini 2.5 Flash Image ("Nano Banana") supports reference-image conditioning,
which we use to keep animation frames visually consistent with a base frame.

Auth: GEMINI_API_KEY env var (or passed explicitly). Google has no workable
Entra equivalent; this path is intentionally simple.

Docs: https://ai.google.dev/gemini-api/docs/image-generation
"""

from __future__ import annotations

import os
import sys
from typing import Optional


DEFAULT_MODEL = "gemini-2.5-flash-image"


def _require_sdk():
    try:
        from google import genai  # type: ignore
        return genai
    except ImportError:
        print(
            "ERROR: google-genai package not installed. Run: pip install google-genai",
            file=sys.stderr,
        )
        sys.exit(1)


def build_client(api_key: Optional[str] = None):
    genai = _require_sdk()
    api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print(
            "ERROR: Gemini requires an API key. Set GEMINI_API_KEY env var or pass --gemini-api-key.",
            file=sys.stderr,
        )
        sys.exit(1)
    return genai.Client(api_key=api_key)


def generate_with_reference(
    client,
    *,
    prompt: str,
    reference_png_bytes: Optional[bytes] = None,
    model: str = DEFAULT_MODEL,
) -> bytes:
    """Call Gemini 2.5 Flash Image with an optional reference image.

    Returns raw PNG bytes of the first inline image in the response.
    """
    from google.genai import types  # type: ignore

    contents: list = [prompt]
    if reference_png_bytes:
        contents.append(types.Part.from_bytes(data=reference_png_bytes, mime_type="image/png"))

    response = client.models.generate_content(
        model=model,
        contents=contents,
    )

    for part in response.candidates[0].content.parts:
        inline = getattr(part, "inline_data", None)
        if inline and getattr(inline, "data", None):
            return inline.data

    raise RuntimeError("Gemini response contained no inline image data")
