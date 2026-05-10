"""fal.ai utility tools — background removal, upscaling, animation, and more.

These tools use fal-hosted models as alternatives to local libraries (rembg,
Pillow resize). They are stateless — callers pass image bytes and get bytes back.

Tools:
  Background removal:
    bg-remove           fal-ai/birefnet (BiRefNet HQ matting)
    bg-remove-bria      fal-ai/bria/background/remove (RMBG 2.0, commercially safe)

  Upscaling:
    upscale             fal-ai/clarity-upscaler (4× generative upscale)
    upscale-seedvr      fal-ai/seedvr/upscale/image (SeedVR2, $0.001/megapixel)
    upscale-topaz       fal-ai/topaz/upscale/image (Topaz professional upscale)

  Animation / video:
    images-to-video     fal-ai/ffmpeg-api/images-to-video (stitch frames → MP4/GIF)
    image-to-video      fal-ai/kling-video/v3/pro/image-to-video (animate still sprite)

  Utilities:
    list_tools()        Return available tool names + descriptions
    run_tool()          Dispatch a named tool against image bytes

Auth: FAL_KEY environment variable (or passed explicitly).
"""

from __future__ import annotations

import os
import sys
import urllib.request
from collections.abc import Sequence

AVAILABLE_TOOLS = {
    # ── Background removal ──
    "bg-remove": {
        "model": "fal-ai/birefnet",
        "description": "BiRefNet HQ background removal (matting)",
        "category": "background",
    },
    "bg-remove-bria": {
        "model": "fal-ai/bria/background/remove",
        "description": "Bria RMBG 2.0 — trained on licensed data, commercially safe",
        "category": "background",
    },
    # ── Upscaling ──
    "upscale": {
        "model": "fal-ai/clarity-upscaler",
        "description": "Clarity AI generative 4× upscale (creative detail enhancement)",
        "category": "upscale",
    },
    "upscale-seedvr": {
        "model": "fal-ai/seedvr/upscale/image",
        "description": "SeedVR2 upscale — $0.001/megapixel, excellent price/quality",
        "category": "upscale",
    },
    "upscale-topaz": {
        "model": "fal-ai/topaz/upscale/image",
        "description": "Topaz professional-grade upscale (highest fidelity)",
        "category": "upscale",
    },
    # ── Animation / video ──
    "images-to-video": {
        "model": "fal-ai/ffmpeg-api/images-to-video",
        "description": "Stitch ordered PNG frames into MP4 video (GIF alternative)",
        "category": "animation",
    },
    "image-to-video": {
        "model": "fal-ai/kling-video/v3/pro/image-to-video",
        "description": "Kling 3.0 Pro — animate a still sprite into cinematic video",
        "category": "animation",
    },
}


def _fal():
    try:
        import fal_client  # type: ignore

        return fal_client
    except ImportError:
        print(
            "ERROR: fal-client package not installed. Run: pip install fal-client",
            file=sys.stderr,
        )
        sys.exit(1)


def _ensure_key(api_key: str | None = None):
    key = api_key or os.environ.get("FAL_KEY")
    if not key:
        print(
            "ERROR: fal.ai requires an API key. Set FAL_KEY env var or pass api_key=...",
            file=sys.stderr,
        )
        sys.exit(1)
    os.environ.setdefault("FAL_KEY", key)
    return key


def _upload_image(fal, image_bytes: bytes, name: str = "image.png") -> str:
    """Upload raw bytes to fal.ai and return a public URL for model input."""
    import io

    buf = io.BytesIO(image_bytes)
    buf.name = name
    url = fal.upload(buf, content_type="image/png")
    return url


# ═══════════════════════════════════════════════════════════════════════════════
#  Background removal
# ═══════════════════════════════════════════════════════════════════════════════


def remove_background(
    image_bytes: bytes,
    *,
    api_key: str | None = None,
    model: str = "fal-ai/birefnet",
) -> bytes:
    """Remove background via a fal.ai model.

    Args:
        image_bytes: PNG/JPEG image bytes.
        api_key: fal.ai key (default: FAL_KEY env var).
        model: 'fal-ai/birefnet' (default) or 'fal-ai/bria/background/remove'.

    Returns:
        PNG bytes with transparent background.
    """
    fal = _fal()
    _ensure_key(api_key)

    image_url = _upload_image(fal, image_bytes)

    result = fal.subscribe(
        model,
        arguments={"image_url": image_url},
    )

    # Different models return results in different shapes.
    output_url = None
    if "image" in result:
        output_url = result["image"].get("url")
    elif "images" in result:
        output_url = result["images"][0].get("url")

    if not output_url:
        raise RuntimeError(f"{model} returned no output image")

    with urllib.request.urlopen(output_url) as r:
        return r.read()


def remove_background_bria(
    image_bytes: bytes,
    *,
    api_key: str | None = None,
) -> bytes:
    """Remove background via Bria RMBG 2.0 (commercially safe, licensed data)."""
    return remove_background(
        image_bytes,
        api_key=api_key,
        model="fal-ai/bria/background/remove",
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Upscaling
# ═══════════════════════════════════════════════════════════════════════════════


def upscale(
    image_bytes: bytes,
    *,
    scale: int = 4,
    api_key: str | None = None,
    model: str = "fal-ai/clarity-upscaler",
) -> bytes:
    """Upscale an image via a fal.ai model.

    Args:
        image_bytes: PNG/JPEG image bytes.
        scale: Upscale factor (2 or 4; default 4).
        api_key: fal.ai key.
        model: One of the upscale models.

    Returns:
        Upscaled PNG bytes.
    """
    fal = _fal()
    _ensure_key(api_key)

    image_url = _upload_image(fal, image_bytes)

    arguments: dict = {"image_url": image_url}
    # SeedVR and Topaz use 'scale'; Clarity also accepts it.
    if model in ("fal-ai/seedvr/upscale/image", "fal-ai/topaz/upscale/image", "fal-ai/clarity-upscaler"):
        arguments["scale"] = scale

    result = fal.subscribe(model, arguments=arguments)

    output_url = result.get("image", {}).get("url")
    if not output_url:
        raise RuntimeError(f"{model} returned no output image")

    with urllib.request.urlopen(output_url) as r:
        return r.read()


def upscale_seedvr(
    image_bytes: bytes,
    *,
    scale: int = 2,
    api_key: str | None = None,
) -> bytes:
    """Upscale via SeedVR2 — $0.001/megapixel, great price/quality ratio."""
    return upscale(
        image_bytes,
        scale=scale,
        api_key=api_key,
        model="fal-ai/seedvr/upscale/image",
    )


def upscale_topaz(
    image_bytes: bytes,
    *,
    scale: int = 4,
    api_key: str | None = None,
) -> bytes:
    """Upscale via Topaz — professional-grade, highest fidelity."""
    return upscale(
        image_bytes,
        scale=scale,
        api_key=api_key,
        model="fal-ai/topaz/upscale/image",
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Animation / video
# ═══════════════════════════════════════════════════════════════════════════════


def images_to_video(
    frame_bytes_list: list[bytes],
    *,
    fps: int = 8,
    hold_frames: int = 15,
    api_key: str | None = None,
) -> bytes:
    """Stitch ordered PNG frames into an MP4 video via fal.ai ffmpeg.

    Perfect for exporting sprite-sheet animations as playable video/GIF
    alternatives. Each frame is held for `hold_frames` video frames at the
    given `fps`.

    Args:
        frame_bytes_list: Ordered list of PNG frame bytes (e.g. walk cycle).
        fps: Video frame rate (default 8 — good for pixel art animation).
        hold_frames: How many video frames to hold each sprite frame.
            At 8 fps with hold=15, each sprite frame shows for ~1.9s.
        api_key: fal.ai key.

    Returns:
        MP4 video bytes.
    """
    fal = _fal()
    _ensure_key(api_key)

    # Upload each frame and collect URLs.
    frame_urls: list[str] = []
    for i, frame_bytes in enumerate(frame_bytes_list):
        url = _upload_image(fal, frame_bytes, name=f"frame_{i:03d}.png")
        frame_urls.append(url)

    result = fal.subscribe(
        "fal-ai/ffmpeg-api/images-to-video",
        arguments={
            "image_urls": frame_urls,
            "fps": fps,
            "hold_frames": hold_frames,
        },
    )

    video_url = result.get("video", {}).get("url")
    if not video_url:
        raise RuntimeError("ffmpeg-api/images-to-video returned no video")

    with urllib.request.urlopen(video_url) as r:
        return r.read()


def image_to_video(
    image_bytes: bytes,
    *,
    prompt: str = "",
    duration: str = "5s",
    api_key: str | None = None,
) -> bytes:
    """Animate a still sprite image into video via Kling 3.0 Pro.

    Args:
        image_bytes: PNG bytes of the sprite to animate.
        prompt: Optional text describing desired motion.
        duration: Video duration ('5s' or '10s').
        api_key: fal.ai key.

    Returns:
        MP4 video bytes.
    """
    fal = _fal()
    _ensure_key(api_key)

    image_url = _upload_image(fal, image_bytes)

    result = fal.subscribe(
        "fal-ai/kling-video/v3/pro/image-to-video",
        arguments={
            "image_url": image_url,
            "prompt": prompt or "subtle idle animation, pixel art character breathing loop",
            "duration": duration,
        },
    )

    video_url = result.get("video", {}).get("url")
    if not video_url:
        raise RuntimeError("kling-video returned no video")

    with urllib.request.urlopen(video_url) as r:
        return r.read()


def list_tools(category: str | None = None) -> dict:
    """Return the available fal.ai utility tools and their descriptions.

    Args:
        category: Filter by category ('background', 'upscale', 'animation')
            or None for all.
    """
    if category:
        return {k: v for k, v in AVAILABLE_TOOLS.items() if v.get("category") == category}
    return dict(AVAILABLE_TOOLS)


def run_tool(
    tool_name: str,
    image_bytes: bytes | Sequence[bytes],
    *,
    api_key: str | None = None,
    **kwargs,
) -> bytes:
    """Dispatch a named tool against image bytes.

    Args:
        tool_name: key in AVAILABLE_TOOLS.
        image_bytes: input image bytes. For 'images-to-video', pass a
            Sequence of frame bytes (e.g. list of PNG blobs).
        api_key: fal.ai key.
        **kwargs: forwarded to the specific tool function.

    Returns:
        Processed image bytes (or video bytes for animation tools).

    Raises:
        ValueError if tool_name is unknown.
    """
    if tool_name not in AVAILABLE_TOOLS:
        raise ValueError(
            f"Unknown fal tool '{tool_name}'. Available: {list(AVAILABLE_TOOLS)}"
        )

    if tool_name == "bg-remove":
        return remove_background(image_bytes, api_key=api_key, **kwargs)  # type: ignore[arg-type]
    if tool_name == "bg-remove-bria":
        return remove_background_bria(image_bytes, api_key=api_key, **kwargs)  # type: ignore[arg-type]
    if tool_name == "upscale":
        return upscale(image_bytes, api_key=api_key, **kwargs)  # type: ignore[arg-type]
    if tool_name == "upscale-seedvr":
        return upscale_seedvr(image_bytes, api_key=api_key, **kwargs)  # type: ignore[arg-type]
    if tool_name == "upscale-topaz":
        return upscale_topaz(image_bytes, api_key=api_key, **kwargs)  # type: ignore[arg-type]
    if tool_name == "images-to-video":
        frames = list(image_bytes) if isinstance(image_bytes, Sequence) else [image_bytes]
        return images_to_video(frames, api_key=api_key, **kwargs)  # type: ignore[arg-type]
    if tool_name == "image-to-video":
        return image_to_video(image_bytes, api_key=api_key, **kwargs)  # type: ignore[arg-type]

    raise ValueError(f"Tool '{tool_name}' not implemented")
