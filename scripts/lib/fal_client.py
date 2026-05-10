"""fal.ai image generation client wrapper.

fal.ai hosts a wide range of generative image models (Flux, Stable Diffusion,
Recraft, Nano Banana, etc.) exposed through a unified REST + WebSocket API.
This module provides the same `build_client` / `generate_image_bytes` /
`resolve_model` interface used by the other provider backends.

Supported models (see MODEL_CATALOG for full list):

  Text-to-image:
    fal-ai/flux/dev              FLUX.1 dev — high quality, open weights (default)
    fal-ai/flux/schnell          FLUX.1 schnell — 4-step distilled, fast
    fal-ai/flux-pro/v1.1-ultra   FLUX1.1 [pro] — highest quality
    fal-ai/recraft/v3/text-to-image  Recraft V3 — SOTA, vector art capable
    fal-ai/recraft/v4/pro/text-to-image  Recraft V4 — designed for production
    fal-ai/nano-banana-pro       Google's latest image gen + edit model
    fal-ai/nano-banana-2         Google's fast gen + edit model
    fal-ai/qwen-image            Qwen — excellent text rendering
    fal-ai/seedream/v4.5/edit    ByteDance unified gen + edit

  Image-to-image / editing:
    fal-ai/flux-pro/kontext      Reference image + text → targeted edits
    fal-ai/nano-banana-pro/edit  Google's best editing model
    fal-ai/reve/edit             Simple image-to-image transform
    fal-ai/bria/fibo-edit/edit   JSON + Mask + Image precise editing

Auth: FAL_KEY environment variable (or passed explicitly).
Docs: https://fal.ai/docs
"""

from __future__ import annotations

import os
import sys
import urllib.request

DEFAULT_MODEL = "fal-ai/flux/dev"

# ── Model catalog: recommended models per use case ──────────────────────────
# Each entry: (model_id, description, generation_type)
# generation_type: 'text-to-image' | 'image-to-image'
MODEL_CATALOG: dict[str, dict] = {
    # ── Text-to-image (primary generation) ──
    "fal-ai/flux/dev": {
        "description": "FLUX.1 dev — high quality, open weights (default)",
        "type": "text-to-image",
        "quality_map": {"low": "fal-ai/flux/schnell", "medium": "fal-ai/flux/schnell", "high": "fal-ai/flux/dev"},
    },
    "fal-ai/flux/schnell": {
        "description": "FLUX.1 schnell — 4-step distilled, fast & cheap",
        "type": "text-to-image",
    },
    "fal-ai/flux-pro/v1.1-ultra": {
        "description": "FLUX1.1 [pro] — highest quality, best composition",
        "type": "text-to-image",
    },
    "fal-ai/recraft/v3/text-to-image": {
        "description": "Recraft V3 — SOTA vector art, brand styles, excellent for pixel art aesthetics",
        "type": "text-to-image",
    },
    "fal-ai/recraft/v4/pro/text-to-image": {
        "description": "Recraft V4 — production-ready, refined lighting & materials",
        "type": "text-to-image",
    },
    "fal-ai/nano-banana-pro": {
        "description": "Nano Banana Pro — Google's latest gen + edit, great realism & typography",
        "type": "text-to-image",
    },
    "fal-ai/nano-banana-2": {
        "description": "Nano Banana 2 — Google's fast gen + edit model",
        "type": "text-to-image",
    },
    "fal-ai/qwen-image": {
        "description": "Qwen-Image — excellent complex text rendering (good for UI/HUD elements)",
        "type": "text-to-image",
    },
    "fal-ai/seedream/v4.5/edit": {
        "description": "Seedream 4.5 — ByteDance unified generation + editing",
        "type": "text-to-image",
    },
    # ── Image-to-image / editing ──
    "fal-ai/flux-pro/kontext": {
        "description": "FLUX Kontext [pro] — reference image + text, targeted local edits",
        "type": "image-to-image",
    },
    "fal-ai/nano-banana-pro/edit": {
        "description": "Nano Banana Pro edit — Google's best image editor, refine existing sprites",
        "type": "image-to-image",
    },
    "fal-ai/reve/edit": {
        "description": "Reve edit — simple image-to-image transform via text prompt",
        "type": "image-to-image",
    },
    "fal-ai/bria/fibo-edit/edit": {
        "description": "Bria FIBO Edit — JSON + Mask + Image, maximum controllability",
        "type": "image-to-image",
    },
}

# Map WIDTHxHEIGHT to fal.ai named image_size presets.
_SIZE_MAP: dict[str, str] = {
    # Square family
    "512x512": "square",
    "1024x1024": "square_hd",
    "2048x2048": "square_2048",
    # Landscape family
    "1024x768": "landscape_4_3",
    "1152x896": "landscape_4_3",
    "1344x768": "landscape_16_9",
    "1536x640": "landscape_16_9",
    # Portrait family
    "768x1024": "portrait_4_3",
    "896x1152": "portrait_4_3",
    "768x1344": "portrait_16_9",
    "640x1536": "portrait_16_9",
}


def list_models(type_filter: str | None = None) -> dict:
    """Return the model catalog, optionally filtered by type.

    Args:
        type_filter: 'text-to-image', 'image-to-image', or None for all.
    """
    if type_filter:
        return {k: v for k, v in MODEL_CATALOG.items() if v.get("type") == type_filter}
    return dict(MODEL_CATALOG)


def _require_sdk():
    try:
        import fal_client  # type: ignore

        return fal_client
    except ImportError:
        print(
            "ERROR: fal-client package not installed. Run: pip install fal-client",
            file=sys.stderr,
        )
        sys.exit(1)


def build_client(api_key: str | None = None):
    """Validate that fal.ai credentials are available.

    Returns the fal_client module (stateless — no client object needed).
    The SDK reads FAL_KEY from the environment automatically.
    """
    fal = _require_sdk()
    api_key = api_key or os.environ.get("FAL_KEY")
    if not api_key:
        print(
            "ERROR: fal.ai requires an API key. Set FAL_KEY env var or pass --fal-api-key.",
            file=sys.stderr,
        )
        sys.exit(1)
    # Set in env so the SDK picks it up transparently.
    os.environ.setdefault("FAL_KEY", api_key)
    return fal


def resolve_model(cli_value: str | None = None) -> str:
    return cli_value or os.environ.get("FAL_MODEL", DEFAULT_MODEL)


def image_size_for_dimensions(size: str) -> str:
    """Map a WIDTHxHEIGHT string to a fal.ai named image_size preset.

    Falls back to 'square_hd' for unrecognised sizes so the call always succeeds.
    """
    return _SIZE_MAP.get(size, "square_hd")


def generate_image_bytes(
    fal,
    *,
    model: str,
    prompt: str,
    size: str = "1024x1024",
    quality: str = "high",
    n: int = 1,
) -> list[bytes]:
    """Generate images via fal.ai and return a list of raw image bytes.

    Args:
        fal: The fal_client module (returned by build_client).
        model: fal.ai model identifier (e.g. 'fal-ai/flux/dev').
        prompt: Text prompt.
        size: WIDTHxHEIGHT (mapped to a fal named size preset).
        quality: 'low'/'medium'/'high' — for Flux family, low/medium switch
            to schnell. For other models, passed as-is.
        n: Number of images (1–4). Some models cap at 1.
    """
    image_size = image_size_for_dimensions(size)

    # Quality → model override via catalog quality_map.
    resolved_model = model
    info = MODEL_CATALOG.get(model, {})
    quality_map = info.get("quality_map", {})
    if quality in quality_map:
        resolved_model = quality_map[quality]

    arguments: dict = {
        "prompt": prompt,
        "image_size": image_size,
        "num_images": min(n, 4),
        "enable_safety_checker": True,
    }

    result = fal.subscribe(resolved_model, arguments=arguments)

    images = result.get("images", [])
    if not images:
        raise RuntimeError(f"fal.ai returned no images for model {resolved_model}")

    out: list[bytes] = []
    for img in images:
        url = img.get("url")
        if not url:
            raise RuntimeError(f"fal.ai image entry missing url: {img}")
        with urllib.request.urlopen(url) as r:
            out.append(r.read())
    return out


def edit_image_bytes(
    fal,
    *,
    model: str,
    prompt: str,
    reference_image_bytes: bytes,
    size: str = "1024x1024",
) -> bytes:
    """Edit an existing image via a fal.ai image-to-image model.

    Uploads the reference image, then calls the editing model with a text
    prompt describing the desired changes. Useful for refining generated
    sprites or applying stylistic transformations.

    Args:
        fal: The fal_client module.
        model: Editing model (e.g. 'fal-ai/nano-banana-pro/edit').
        prompt: Edit instruction (e.g. 'make this sprite look like SNES style').
        reference_image_bytes: PNG/JPEG bytes of the image to edit.
        size: Output size (mapped to fal named preset).

    Returns:
        Edited image as raw PNG bytes.
    """
    import io

    # Upload reference image to fal.ai storage.
    buf = io.BytesIO(reference_image_bytes)
    buf.name = "reference.png"
    reference_url = fal.upload(buf, content_type="image/png")

    image_size = image_size_for_dimensions(size)

    result = fal.subscribe(
        model,
        arguments={
            "prompt": prompt,
            "image_url": reference_url,
            "image_size": image_size,
        },
    )

    images = result.get("images", [])
    if not images:
        raise RuntimeError(f"fal.ai edit returned no images for model {model}")

    url = images[0].get("url")
    if not url:
        raise RuntimeError(f"fal.ai edit image entry missing url: {images[0]}")

    with urllib.request.urlopen(url) as r:
        return r.read()
