"""Shared image generation option helpers."""

from __future__ import annotations

import argparse

DEFAULT_IMAGE_SIZE = "1024x1024"
POPULAR_IMAGE_SIZES = [
    "1024x1024",
    "1536x1024",
    "1024x1536",
    "2048x2048",
    "2048x1152",
    "3840x2160",
    "2160x3840",
    "auto",
]


def validate_image_size(value: str) -> str:
    """Validate gpt-image-2 size constraints while keeping `auto` available."""
    if value == "auto":
        return value

    try:
        width_s, height_s = value.lower().split("x", 1)
        width = int(width_s)
        height = int(height_s)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "size must be WIDTHxHEIGHT, for example 1024x1024, or auto"
        ) from exc

    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("size dimensions must be positive")
    if width > 3840 or height > 3840:
        raise argparse.ArgumentTypeError("size dimensions must be <= 3840px")
    if width % 16 or height % 16:
        raise argparse.ArgumentTypeError("size dimensions must be multiples of 16")
    if max(width, height) / min(width, height) > 3:
        raise argparse.ArgumentTypeError("size aspect ratio must be no more than 3:1")

    pixels = width * height
    if pixels < 655_360:
        raise argparse.ArgumentTypeError("size must be at least 655,360 total pixels")
    if pixels > 8_294_400:
        raise argparse.ArgumentTypeError("size must be at most 8,294,400 total pixels")

    return f"{width}x{height}"
