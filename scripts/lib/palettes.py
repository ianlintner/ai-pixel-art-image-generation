"""Named palettes for pixel-art quantization.

Each palette is a list of #RRGGBB strings. Provides:
- `get_palette(name) -> list[str]`
- `build_palette_image(hex_list) -> PIL.Image` — a "P" mode image suitable
  as the `palette` argument to `Image.quantize(palette=...)`.

Sources:
- DB16 / DB32: Dawnbringer palettes (lospec.com)
- PICO-8: Lexaloffle PICO-8 official 16 colors
- NES: canonical 54-color NES palette (approximation)
- GAMEBOY: 4-shade monochrome green
- AAP-64: Adigun Polack 64-color palette
"""

from __future__ import annotations

import hashlib
import random
import re

DB16: list[str] = [
    "#140c1c",
    "#442434",
    "#30346d",
    "#4e4a4e",
    "#854c30",
    "#346524",
    "#d04648",
    "#757161",
    "#597dce",
    "#d27d2c",
    "#8595a1",
    "#6daa2c",
    "#d2aa99",
    "#6dc2ca",
    "#dad45e",
    "#deeed6",
]

DB32: list[str] = [
    "#000000",
    "#222034",
    "#45283c",
    "#663931",
    "#8f563b",
    "#df7126",
    "#d9a066",
    "#eec39a",
    "#fbf236",
    "#99e550",
    "#6abe30",
    "#37946e",
    "#4b692f",
    "#524b24",
    "#323c39",
    "#3f3f74",
    "#306082",
    "#5b6ee1",
    "#639bff",
    "#5fcde4",
    "#cbdbfc",
    "#ffffff",
    "#9badb7",
    "#847e87",
    "#696a6a",
    "#595652",
    "#76428a",
    "#ac3232",
    "#d95763",
    "#d77bba",
    "#8f974a",
    "#8a6f30",
]

PICO8: list[str] = [
    "#000000",
    "#1d2b53",
    "#7e2553",
    "#008751",
    "#ab5236",
    "#5f574f",
    "#c2c3c7",
    "#fff1e8",
    "#ff004d",
    "#ffa300",
    "#ffec27",
    "#00e436",
    "#29adff",
    "#83769c",
    "#ff77a8",
    "#ffccaa",
]

GAMEBOY: list[str] = [
    "#0f380f",
    "#306230",
    "#8bac0f",
    "#9bbc0f",
]

NES: list[str] = [
    "#7c7c7c",
    "#0000fc",
    "#0000bc",
    "#4428bc",
    "#940084",
    "#a80020",
    "#a81000",
    "#881400",
    "#503000",
    "#007800",
    "#006800",
    "#005800",
    "#004058",
    "#000000",
    "#000000",
    "#000000",
    "#bcbcbc",
    "#0078f8",
    "#0058f8",
    "#6844fc",
    "#d800cc",
    "#e40058",
    "#f83800",
    "#e45c10",
    "#ac7c00",
    "#00b800",
    "#00a800",
    "#00a844",
    "#008888",
    "#000000",
    "#000000",
    "#000000",
    "#f8f8f8",
    "#3cbcfc",
    "#6888fc",
    "#9878f8",
    "#f878f8",
    "#f85898",
    "#f87858",
    "#fca044",
    "#f8b800",
    "#b8f818",
    "#58d854",
    "#58f898",
    "#00e8d8",
    "#787878",
    "#000000",
    "#000000",
    "#fcfcfc",
    "#a4e4fc",
    "#b8b8f8",
    "#d8b8f8",
    "#f8b8f8",
    "#f8a4c0",
    "#f0d0b0",
    "#fce0a8",
    "#f8d878",
    "#d8f878",
    "#b8f8b8",
    "#b8f8d8",
    "#00fcfc",
    "#f8d8f8",
    "#000000",
    "#000000",
]

AAP64: list[str] = [
    "#060608",
    "#141013",
    "#3b1725",
    "#73172d",
    "#b4202a",
    "#df3e23",
    "#fa6a0a",
    "#f9a31b",
    "#ffd541",
    "#fffc40",
    "#d6f264",
    "#9cdb43",
    "#59c135",
    "#14a02e",
    "#1a7a3e",
    "#24523b",
    "#122020",
    "#143464",
    "#285cc4",
    "#249fde",
    "#20d6c7",
    "#a6fcdb",
    "#ffffff",
    "#fef3c0",
    "#fad6b8",
    "#f5a097",
    "#e86a73",
    "#bc4a9b",
    "#793a80",
    "#403353",
    "#242234",
    "#221c1a",
    "#322b28",
    "#71413b",
    "#bb7547",
    "#dba463",
    "#f4d29c",
    "#dae0ea",
    "#b3b9d1",
    "#8b93af",
    "#6d758d",
    "#4a5462",
    "#333941",
    "#422433",
    "#5b3138",
    "#8e5252",
    "#ba756a",
    "#e9b5a3",
    "#e3e6ff",
    "#b9bffb",
    "#849be4",
    "#588dbe",
    "#477d85",
    "#23674e",
    "#328464",
    "#5daf8d",
    "#92dcba",
    "#cdf7e2",
    "#e4d2aa",
    "#c7b08b",
    "#a08662",
    "#796755",
    "#5a4e44",
    "#423934",
]

PALETTES: dict[str, list[str]] = {
    "db16": DB16,
    "db32": DB32,
    "pico8": PICO8,
    "gameboy": GAMEBOY,
    "nes": NES,
    "aap64": AAP64,
}


def list_palettes() -> list[str]:
    return sorted(PALETTES.keys())


def get_palette(name: str) -> list[str]:
    key = name.lower()
    if key not in PALETTES:
        raise ValueError(f"Unknown palette '{name}'. Available: {list_palettes()}")
    return PALETTES[key]


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def build_palette_image(hex_list: list[str]):
    """Build a PIL 'P' mode image usable as `Image.quantize(palette=...)`.

    PIL requires a palette image with exactly 256 color slots. Unused slots
    are padded to black. First len(hex_list) slots hold the palette entries,
    in order, so index 0 through len-1 map to user colors.
    """
    from PIL import Image

    flat: list[int] = []
    for h in hex_list:
        flat.extend(_hex_to_rgb(h))
    # Pad unused slots with a duplicate of palette[0] rather than (0,0,0).
    # Reason: Image.quantize may pick any slot whose RGB best matches the
    # input pixel. Pure-black padding introduces (0,0,0) as a valid output
    # color even when the real palette lacks it (e.g. db16 starts at #140c1c),
    # causing palette_fidelity < 1.0. Duplicating slot 0 keeps output strictly
    # within the declared palette.
    pad_slots = 256 - len(hex_list)
    pad_rgb = _hex_to_rgb(hex_list[0]) if hex_list else (0, 0, 0)
    flat.extend(list(pad_rgb) * pad_slots)

    palette_img = Image.new("P", (1, 1))
    palette_img.putpalette(flat)
    return palette_img


# Keyword → candidate palettes. Evaluated in order; first hit wins. Each
# entry lists palettes that are *compatible* with the subject so `auto` can
# randomly pick one per variant (seeded) for variety without breaking the
# "palette has mid-luminance grays for stone" kind of invariants.
# First palette in each list is the historical default and is preserved for
# back-compatibility when the RNG is not seeded.
_KEYWORD_PALETTE_TABLE: list[tuple[str, list[str]]] = [
    (r"\b(metal|steel|armor|stone|grey|gray|silver|iron|dungeon|rock|brick)\b", ["db32", "aap64"]),
    (r"\b(tropical|beach|coral|jungle|aquatic|underwater|reef)\b", ["aap64", "db32"]),
    (r"\b(gameboy|monochrome|green\s*only)\b", ["gameboy"]),
    (r"\b(arcade|nes|8-bit|8bit)\b", ["nes", "pico8"]),
    (r"\b(knight|fantasy|rpg|character|hero|warrior|wizard|mage)\b", ["db16", "db32", "aap64"]),
    (r"\b(terrain|tile|overworld|map|landscape|biome)\b", ["db32", "aap64"]),
    (r"\b(detailed|portrait|high-?detail|hi-?detail)\b", ["aap64", "db32"]),
]

_DEFAULT_PALETTE_CANDIDATES = ["db32", "aap64"]
_DEFAULT_PALETTE = _DEFAULT_PALETTE_CANDIDATES[0]


def resolve_palette_candidates(prompt: str) -> tuple[list[str], str]:
    """Return (list_of_compatible_palettes, matched_keyword_or_default)."""
    lowered = prompt.lower()
    for pattern, palettes in _KEYWORD_PALETTE_TABLE:
        m = re.search(pattern, lowered)
        if m:
            return list(palettes), m.group(0)
    return list(_DEFAULT_PALETTE_CANDIDATES), "default"


def suggest_palette(prompt: str) -> tuple[str, str]:
    """Pick the default palette for a subject. (First candidate in table.)

    Returns (palette_name, matched_keyword_or_default).
    """
    candidates, reason = resolve_palette_candidates(prompt)
    return candidates[0], reason


def _seeded_rng_for_palette(seed_str: str) -> random.Random:
    h = hashlib.blake2b(seed_str.encode("utf-8"), digest_size=8).digest()
    return random.Random(int.from_bytes(h, "big"))


def resolve_palette(
    palette_arg: str,
    prompt: str,
    *,
    seed_str: str | None = None,
) -> str:
    """Resolve user --palette arg, handling 'auto' via keyword candidates.

    When `palette_arg == 'auto'`:
      - If `seed_str` is None: returns the historical default (first candidate),
        preserving pre-variation behavior.
      - If `seed_str` is given: seeded RNG picks one candidate uniformly, so
        re-running with the same seed_str yields the same palette but different
        seed_str values produce different palettes.

    Explicit palette names (db16, pico8, etc.) are returned unchanged.
    """
    import sys as _sys

    if palette_arg.lower() == "auto":
        candidates, reason = resolve_palette_candidates(prompt)
        if seed_str is None or len(candidates) == 1:
            chosen = candidates[0]
            print(
                f"[palette] auto → '{chosen}' (matched: {reason})",
                file=_sys.stderr,
            )
            return chosen
        rng = _seeded_rng_for_palette(seed_str)
        chosen = rng.choice(candidates)
        print(
            f"[palette] auto → '{chosen}' (matched: {reason}, seeded pick from {candidates})",
            file=_sys.stderr,
        )
        return chosen
    return palette_arg


# ---------------------------------------------------------------------------
# Palette jitter (Tier 2G): tiny controlled perturbation of hue/lightness so
# two variants of the same sprite don't feel color-identical. Stays within
# sane gamut and avoids touching pure black/white which act as anchor colors.
# ---------------------------------------------------------------------------


def _rgb_to_hls(r: int, g: int, b: int) -> tuple[float, float, float]:
    import colorsys

    return colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)


def _hls_to_rgb(h: float, lt: float, s: float) -> tuple[int, int, int]:
    import colorsys

    r, g, b = colorsys.hls_to_rgb(h, lt, s)
    return (
        max(0, min(255, int(round(r * 255)))),
        max(0, min(255, int(round(g * 255)))),
        max(0, min(255, int(round(b * 255)))),
    )


def jitter_palette(palette_hex: list[str], seed_str: str, strength: float = 0.05) -> list[str]:
    """Return a lightly-perturbed copy of `palette_hex`.

    Shifts hue within ±strength (wraps) and lightness within ±strength*0.5.
    Skips entries that are near-black or near-white to preserve anchor tones.
    Deterministic given `seed_str`.

    Args:
        palette_hex: List of "#rrggbb" entries.
        seed_str: RNG seed string.
        strength: 0..1. 0.05 is gentle (keeps identity), 0.15 is bold.
    """
    strength = max(0.0, min(1.0, float(strength)))
    if strength == 0.0:
        return list(palette_hex)

    rng = _seeded_rng_for_palette(seed_str + "|jitter")
    out: list[str] = []
    for entry in palette_hex:
        r, g, b = _hex_to_rgb(entry)
        # Anchor colors: preserve exactly.
        if max(r, g, b) >= 245 and min(r, g, b) >= 230:
            out.append(entry)
            continue
        if max(r, g, b) <= 16:
            out.append(entry)
            continue
        h, lt, s = _rgb_to_hls(r, g, b)
        h = (h + rng.uniform(-strength, strength)) % 1.0
        lt = max(0.0, min(1.0, lt + rng.uniform(-strength * 0.5, strength * 0.5)))
        # Keep saturation roughly intact; nudge slightly to break ties.
        s = max(0.0, min(1.0, s + rng.uniform(-strength * 0.25, strength * 0.25)))
        nr, ng, nb = _hls_to_rgb(h, lt, s)
        out.append(f"#{nr:02x}{ng:02x}{nb:02x}")
    return out
