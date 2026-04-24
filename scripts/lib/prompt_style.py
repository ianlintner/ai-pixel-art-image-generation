"""Style sampling for pixel-art prompts.

The gpt-image-2 API does not expose `temperature` or `seed`. To get output
variation, we rotate *stylistic* clauses in the prompt suffix while keeping
the load-bearing constraints (no text, no watermark, no borders, plain
background, pixel art) constant. A per-variant seeded RNG picks one value
from each axis so re-runs are reproducible given the same seed string.

Presets compose default axis picks for well-known aesthetics (chibi,
hi-bit-snes, gb-4color, mega-drive, modern-indie). Presets do NOT lock
every axis — they bias the pools so random picks still land in-aesthetic.

`rewrite_prompt` optionally calls a cheap text model (gpt-4.1-mini) to
rephrase the user's subject description per-variant. This is the closest
analog to "temperature" for an image pipeline.
"""

from __future__ import annotations

import hashlib
import random
import sys
from collections.abc import Iterable

# Axes of variation. Each axis is a list of phrases; one is picked per variant.
# IMPORTANT: every phrase here must be compatible with the other axes and with
# the load-bearing constraints in `_CORE_CONSTRAINTS`. Do not introduce phrases
# that contradict "pixel art", "limited palette", or "hard edges" — those are
# the project's identity and must not be diluted by style sampling.
STYLE_AXES: dict[str, list[str]] = {
    "rendering": [
        "clean hard edges",
        "subtle dithering in midtones",
        "chunky blocky shapes with minimal anti-aliasing",
        "soft pillow shading",
        "bold cel-shaded blocks",
        "crisp silhouette with 1-pixel highlights",
        "cross-hatched dithering on shadows",
    ],
    "lighting": [
        "flat uniform lighting",
        "top-down key light",
        "side-lit dramatic rim",
        "soft ambient fill",
        "warm rim light from lower-right",
        "cool moonlight from upper-left",
        "golden-hour backlight",
        "overcast diffuse light",
    ],
    "mood": [
        "heroic",
        "melancholic",
        "whimsical",
        "menacing",
        "serene",
        "playful",
        "mysterious",
        "determined",
    ],
    "angle": [
        "3/4 view",
        "front-facing",
        "side profile",
        "slight high angle",
        "slight low angle",
    ],
    "detail": [
        "minimal detail, iconic silhouette",
        "medium detail with readable features",
        "high detail with visible texture and trim",
    ],
}

# Tileset-specific axes. Tiles should NOT get character-specific mood/angle
# picks but do benefit from surface-material variety.
TILE_STYLE_AXES: dict[str, list[str]] = {
    "rendering": [
        "clean hard edges",
        "subtle dithering on midtones",
        "chunky blocky shapes",
        "crisp 1-pixel highlights and shadows",
        "cross-hatched dithering",
    ],
    "lighting": [
        "flat uniform lighting",
        "top-down key light",
        "soft diffuse ambient",
        "warm directional light",
        "cool directional light",
    ],
    "wear": [
        "pristine and clean",
        "lightly weathered",
        "worn with scattered detail",
        "mossy and overgrown edges",
        "cracked with fine texture",
    ],
    "scale": [
        "small-scale detail",
        "medium-scale detail",
        "broad shapes with few accent pixels",
    ],
}

# Core constraints that must appear in every suffix regardless of style pick.
# These are the project's identity. Do not parametrize them.
_CORE_CONSTRAINTS_SPRITE = (
    "pixel art sprite, limited palette, no text, no watermark, no borders, "
    "no shadows on the ground, plain flat solid-color background, centered, "
    "subject fills the frame edge-to-edge with minimal empty background"
)

_CORE_CONSTRAINTS_TILE = (
    "flat pixel art, limited palette, part of a large seamless tiling surface, "
    "top-down game texture, uniform coverage, no border, no frame, "
    "no UI chrome, no text, no watermark, transparent or solid flat background"
)

_CORE_CONSTRAINTS_ANIMATION = (
    "pixel art sprite, side view, limited palette, "
    "character fills the frame edge-to-edge with minimal empty space around silhouette, "
    "plain flat solid-color background, no text, no watermark, no ground shadow, centered"
)


# Style presets bias axis pools. A preset with `rendering=["..."]` means that
# axis has exactly that list of acceptable phrases; omit an axis to let it
# default to the full STYLE_AXES pool. Presets also carry a palette hint and
# outline default used by generators.
STYLE_PRESETS: dict[str, dict] = {
    "chibi": {
        "description": "Oversized head, stubby body, cute readable shapes",
        "axes": {
            "rendering": ["clean hard edges", "soft pillow shading"],
            "detail": ["minimal detail, iconic silhouette"],
            "mood": ["whimsical", "playful", "heroic"],
        },
        "palette_hint": "db16",
        "outline_default": "palette-darkest",
        "extra_clauses": ["chibi proportions, oversized head, stubby limbs"],
    },
    "hi-bit-snes": {
        "description": "SNES-era 16-bit with dithering and rich mid-tones",
        "axes": {
            "rendering": [
                "subtle dithering in midtones",
                "cross-hatched dithering on shadows",
                "crisp silhouette with 1-pixel highlights",
            ],
            "detail": [
                "medium detail with readable features",
                "high detail with visible texture and trim",
            ],
        },
        "palette_hint": "aap64",
        "outline_default": "tone-shift",
        "extra_clauses": ["16-bit SNES aesthetic, visible dithering"],
    },
    "gb-4color": {
        "description": "Game Boy 4-shade green monochrome",
        "axes": {
            "rendering": ["clean hard edges", "chunky blocky shapes with minimal anti-aliasing"],
            "lighting": ["flat uniform lighting"],
            "detail": ["minimal detail, iconic silhouette"],
        },
        "palette_hint": "gameboy",
        "outline_default": "palette-darkest",
        "extra_clauses": ["4-shade monochrome green palette, original Game Boy aesthetic"],
    },
    "mega-drive": {
        "description": "Sega Genesis/Mega Drive punchy saturated 16-bit",
        "axes": {
            "rendering": [
                "bold cel-shaded blocks",
                "crisp silhouette with 1-pixel highlights",
            ],
            "detail": ["medium detail with readable features"],
        },
        "palette_hint": "db32",
        "outline_default": "palette-darkest",
        "extra_clauses": ["Sega Genesis 16-bit aesthetic, saturated bold colors"],
    },
    "modern-indie": {
        "description": "Contemporary indie pixel art, clean with selective dithering",
        "axes": {
            "rendering": [
                "clean hard edges",
                "subtle dithering in midtones",
                "crisp silhouette with 1-pixel highlights",
            ],
        },
        "palette_hint": "aap64",
        "outline_default": "tone-shift",
        "extra_clauses": ["modern indie pixel art"],
    },
    "nes": {
        "description": "NES-era 8-bit, limited palette, chunky shapes",
        "axes": {
            "rendering": ["chunky blocky shapes with minimal anti-aliasing"],
            "detail": ["minimal detail, iconic silhouette"],
            "lighting": ["flat uniform lighting"],
        },
        "palette_hint": "nes",
        "outline_default": "palette-darkest",
        "extra_clauses": ["8-bit NES aesthetic, 4-color-per-sprite limitation feel"],
    },
}


def list_style_presets() -> list[str]:
    return sorted(STYLE_PRESETS.keys())


def _seeded_rng(seed_str: str) -> random.Random:
    """Deterministic RNG keyed by a string. Same seed_str → same picks."""
    h = hashlib.blake2b(seed_str.encode("utf-8"), digest_size=8).digest()
    return random.Random(int.from_bytes(h, "big"))


def _pick(rng: random.Random, pool: Iterable[str]) -> str:
    pool_list = list(pool)
    if not pool_list:
        return ""
    return rng.choice(pool_list)


def sample_style(
    seed_str: str,
    *,
    preset: str | None = None,
    kind: str = "sprite",
) -> dict:
    """Sample one phrase per axis using a seeded RNG.

    Args:
        seed_str: Deterministic seed, e.g. f"{prompt}|{variant_idx}".
        preset: Optional STYLE_PRESETS key to constrain axis pools.
        kind: 'sprite' | 'animation' use STYLE_AXES; 'tile' uses TILE_STYLE_AXES.

    Returns: dict with keys = axis names, values = chosen phrase, plus
             '_preset' and '_extra_clauses' metadata keys.
    """
    rng = _seeded_rng(seed_str)
    axes = TILE_STYLE_AXES if kind == "tile" else STYLE_AXES
    preset_axes: dict[str, list[str]] = {}
    extra_clauses: list[str] = []
    if preset:
        preset = preset.lower()
        if preset not in STYLE_PRESETS:
            raise ValueError(f"Unknown style preset '{preset}'. Available: {list_style_presets()}")
        preset_axes = STYLE_PRESETS[preset].get("axes", {})
        extra_clauses = list(STYLE_PRESETS[preset].get("extra_clauses", []))

    chosen: dict = {}
    for axis_name, default_pool in axes.items():
        pool = preset_axes.get(axis_name, default_pool)
        chosen[axis_name] = _pick(rng, pool)

    chosen["_preset"] = preset or None
    chosen["_extra_clauses"] = extra_clauses
    chosen["_seed"] = seed_str
    chosen["_kind"] = kind
    return chosen


def compose_suffix(style: dict, *, kind: str = "sprite") -> str:
    """Build the prompt suffix for a given kind using style choices.

    Stylistic axes are joined first (they bias aesthetic), then the core
    constraints, then any preset-supplied extra clauses. Core constraints
    come last so they read as the strongest / most recent instruction.
    """
    if kind == "sprite":
        axis_order = ["angle", "mood", "rendering", "lighting", "detail"]
        core = _CORE_CONSTRAINTS_SPRITE
    elif kind == "tile":
        axis_order = ["scale", "wear", "rendering", "lighting"]
        core = _CORE_CONSTRAINTS_TILE
    elif kind == "animation":
        axis_order = ["mood", "rendering", "lighting", "detail"]
        core = _CORE_CONSTRAINTS_ANIMATION
    else:
        raise ValueError(f"Unknown kind '{kind}'")

    axis_phrases = [style[a] for a in axis_order if style.get(a)]
    extras = style.get("_extra_clauses", []) or []
    parts: list[str] = []
    if axis_phrases:
        parts.append(", ".join(axis_phrases))
    if extras:
        parts.append(", ".join(extras))
    parts.append(core)
    # Leading space so this appends cleanly after "<prompt>."
    return " " + ". ".join(parts) + "."


def resolve_style(
    preset: str | None,
    seed_str: str,
    *,
    kind: str = "sprite",
) -> dict:
    """One-call helper: sample style using preset + seed for a given kind."""
    return sample_style(seed_str, preset=preset, kind=kind)


# ---------------------------------------------------------------------------
# Optional LLM-driven prompt rewrite (Tier 2E)
# ---------------------------------------------------------------------------


_REWRITE_MODEL_DEFAULT = "gpt-4.1-mini"

_REWRITE_SYSTEM = (
    "You rewrite pixel-art subject descriptions for variation. "
    "Keep the subject identity (species, gender, role, signature gear). "
    "Change exactly ONE of: pose, silhouette emphasis, expression, or secondary props. "
    "Keep it one sentence, under 30 words, no quotes, no preamble. "
    "Do not mention pixel art, style, palette, or frame — those are added separately."
)


def rewrite_prompt(
    openai_client,
    base_prompt: str,
    variant_idx: int,
    *,
    model: str = _REWRITE_MODEL_DEFAULT,
) -> str:
    """Ask a cheap text model to rephrase `base_prompt` for variant variety.

    Gracefully falls back to `base_prompt` on any error (missing model,
    auth, network, unexpected response shape). Prints a stderr note so
    failures are visible without aborting the pipeline.
    """
    if variant_idx == 0:
        # Variant 0 always uses the original prompt verbatim so at least one
        # output matches the user's exact wording.
        return base_prompt
    try:
        instruction = f"Rewrite variant #{variant_idx} of: {base_prompt}"
        resp = openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _REWRITE_SYSTEM},
                {"role": "user", "content": instruction},
            ],
            temperature=0.9,
            max_tokens=80,
        )
        text = (resp.choices[0].message.content or "").strip().strip('"').strip()
        if not text:
            return base_prompt
        return text
    except Exception as e:  # noqa: BLE001 — fallback must be total
        print(
            f"[prompt-rewrite] fallback to original prompt (model={model}): {e}",
            file=sys.stderr,
        )
        return base_prompt
