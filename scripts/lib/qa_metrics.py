"""Pure-Pillow QA metrics for pixel-art artifacts.

No NumPy dependency — the images are small (≤256 px) so per-pixel Python
loops are fast enough. No network calls; all metrics are local.

Each metric returns a float or bool. Thresholds (hard vs. soft gates) are
declared in `GATES` at the bottom of this file and consumed by the CLI.
"""

from __future__ import annotations

from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def _opaque_pixels(img):
    """Yield (x, y, (r, g, b)) for every opaque pixel (alpha >= 128)."""
    rgba = img.convert("RGBA")
    w, h = rgba.size
    px = rgba.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a >= 128:
                yield x, y, (r, g, b)


def _palette_rgb_set(palette_hex: List[str]) -> set:
    out = set()
    for h in palette_hex:
        h = h.lstrip("#")
        out.add((int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))
    return out


def _luminance(rgb):
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


# ---------------------------------------------------------------------------
# Metrics shared by all artifact kinds
# ---------------------------------------------------------------------------


def palette_fidelity(img, palette_hex: List[str]) -> float:
    """Fraction of opaque pixels whose RGB is a palette entry. 1.0 is perfect."""
    pal = _palette_rgb_set(palette_hex)
    total = 0
    ok = 0
    for _, _, rgb in _opaque_pixels(img):
        total += 1
        if rgb in pal:
            ok += 1
    return ok / total if total else 1.0


def alpha_crispness(img) -> float:
    """Fraction of alpha values that are 0 or 255. 1.0 is perfect."""
    rgba = img.convert("RGBA")
    alpha = rgba.split()[-1]
    w, h = alpha.size
    ap = alpha.load()
    total = w * h
    crisp = 0
    for y in range(h):
        for x in range(w):
            a = ap[x, y]
            if a == 0 or a == 255:
                crisp += 1
    return crisp / total


def palette_coverage(img, palette_hex: List[str]) -> float:
    """Unique opaque colours / palette size. Warn if <0.15 or >0.60 for sprites."""
    uniq = set()
    for _, _, rgb in _opaque_pixels(img):
        uniq.add(rgb)
    return len(uniq) / len(palette_hex) if palette_hex else 0.0


# ---------------------------------------------------------------------------
# Tileset metrics
# ---------------------------------------------------------------------------


def tile_seam_diff(tile_img) -> float:
    """Mean L2 RGB distance between wrap-adjacent edges (0-255 scale)."""
    import math

    rgba = tile_img.convert("RGBA")
    w, h = rgba.size
    px = rgba.load()
    total = 0.0
    count = 0
    for y in range(h):
        a = px[0, y]
        b = px[w - 1, y]
        total += math.sqrt(
            (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
        )
        count += 1
    for x in range(w):
        a = px[x, 0]
        b = px[x, h - 1]
        total += math.sqrt(
            (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2
        )
        count += 1
    return total / count if count else 0.0


def sheet_per_tile_seam_diffs(
    sheet_img, tile_size: int, columns: int, tile_count: int
) -> List[float]:
    """Split a tileset sheet into tiles and return seam_diff for each."""
    results = []
    rows = (tile_count + columns - 1) // columns
    for r in range(rows):
        for c in range(columns):
            idx = r * columns + c
            if idx >= tile_count:
                break
            left = c * tile_size
            top = r * tile_size
            tile = sheet_img.crop((left, top, left + tile_size, top + tile_size))
            results.append(tile_seam_diff(tile))
    return results


# ---------------------------------------------------------------------------
# Sprite metrics
# ---------------------------------------------------------------------------


def outline_coverage(img, palette_hex: List[str]) -> float:
    """Fraction of opaque-boundary pixels that are in darkest quartile of palette.

    Opaque-boundary pixel = opaque pixel with ≥1 transparent 4-neighbour.
    Target: ≥ 0.85 indicates a deliberate dark outline ring.
    """
    rgba = img.convert("RGBA")
    w, h = rgba.size
    px = rgba.load()

    # Build luminance-sorted palette; the darkest quartile is our outline band.
    pal = sorted(_palette_rgb_set(palette_hex), key=_luminance)
    if not pal:
        return 0.0
    quartile_size = max(1, len(pal) // 4)
    dark_band = set(pal[:quartile_size])

    def is_transparent(x, y):
        if x < 0 or y < 0 or x >= w or y >= h:
            return True
        return px[x, y][3] < 128

    boundary = 0
    dark = 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a < 128:
                continue
            # 4-neighbour boundary check.
            if (
                is_transparent(x - 1, y)
                or is_transparent(x + 1, y)
                or is_transparent(x, y - 1)
                or is_transparent(x, y + 1)
            ):
                boundary += 1
                if (r, g, b) in dark_band:
                    dark += 1
    return dark / boundary if boundary else 1.0


def baseline_alignment(img, min_contiguous: int = 3) -> bool:
    """Lowest opaque row must have ≥ min_contiguous horizontally contiguous px."""
    rgba = img.convert("RGBA")
    w, h = rgba.size
    px = rgba.load()
    for y in range(h - 1, -1, -1):
        # Build boolean row.
        row = [px[x, y][3] >= 128 for x in range(w)]
        if any(row):
            # Find longest run.
            run = best = 0
            for v in row:
                run = run + 1 if v else 0
                best = max(best, run)
            return best >= min_contiguous
    return False


# ---------------------------------------------------------------------------
# Animation metrics
# ---------------------------------------------------------------------------


def _alpha_mask(img) -> List[List[bool]]:
    rgba = img.convert("RGBA")
    w, h = rgba.size
    px = rgba.load()
    return [[px[x, y][3] >= 128 for x in range(w)] for y in range(h)]


def silhouette_iou(img_a, img_b) -> float:
    """Intersection over union between two alpha masks (must be same size)."""
    a = _alpha_mask(img_a)
    b = _alpha_mask(img_b)
    h, w = len(a), len(a[0]) if a else 0
    inter = union = 0
    for y in range(h):
        for x in range(w):
            ai, bi = a[y][x], b[y][x]
            if ai or bi:
                union += 1
            if ai and bi:
                inter += 1
    return inter / union if union else 1.0


def _alpha_bbox(img) -> Tuple[int, int, int, int]:
    """Return (left, top, right, bottom) of opaque region, or None if empty."""
    rgba = img.convert("RGBA")
    w, h = rgba.size
    px = rgba.load()
    left = w
    right = -1
    top = h
    bottom = -1
    for y in range(h):
        for x in range(w):
            if px[x, y][3] >= 128:
                if x < left: left = x
                if x > right: right = x
                if y < top: top = y
                if y > bottom: bottom = y
    if right < 0:
        return (0, 0, 0, 0)
    return (left, top, right, bottom)


def bbox_drift(frame_imgs: List) -> int:
    """Max per-axis px drift of bbox across frames (relative to frame 0).

    Legacy combined metric. Walk-cycle physics make this noisy because
    contact vs. passing poses naturally differ in silhouette width (legs
    extended vs. crossed). Prefer bbox_drift_xy for hard gating.
    """
    if not frame_imgs:
        return 0
    bboxes = [_alpha_bbox(f) for f in frame_imgs]
    base = bboxes[0]
    worst = 0
    for bb in bboxes[1:]:
        for i in range(4):
            diff = abs(bb[i] - base[i])
            if diff > worst:
                worst = diff
    return worst


def bbox_drift_xy(frame_imgs: List) -> Tuple[int, int]:
    """Return (x_drift, y_drift) separately.

    x_drift: max absolute diff of left/right bounds vs. frame 0. Expected to
        be non-trivial on walk cycles (leg extension widens silhouette on
        contact frames, narrows it on passing frames).
    y_drift: max absolute diff of top/bottom bounds vs. frame 0. Should stay
        tight (≤ 2 px) — accounts for 1-px bob on passing frames but catches
        character drifting vertically in-frame.
    """
    if not frame_imgs:
        return 0, 0
    bboxes = [_alpha_bbox(f) for f in frame_imgs]
    base = bboxes[0]
    x_worst = 0
    y_worst = 0
    for bb in bboxes[1:]:
        x_worst = max(x_worst, abs(bb[0] - base[0]), abs(bb[2] - base[2]))
        y_worst = max(y_worst, abs(bb[1] - base[1]), abs(bb[3] - base[3]))
    return x_worst, y_worst


# ---------------------------------------------------------------------------
# Reporting orchestration
# ---------------------------------------------------------------------------


# Gate definitions. 'op' indicates pass direction: 'ge'=>=, 'le'=<=, 'eq'==, 'between' requires [lo,hi].
GATES: Dict[str, dict] = {
    "palette_fidelity": {"op": "eq", "value": 1.0, "hard": True},
    "alpha_crispness": {"op": "ge", "value": 0.999, "hard": True},
    "tile_seam_diff_mean": {"op": "le", "value": 12.0, "hard": True},
    "outline_coverage": {"op": "ge", "value": 0.85, "hard": False},
    "baseline_alignment": {"op": "eq", "value": True, "hard": True},
    "palette_coverage": {"op": "between", "value": [0.15, 0.60], "hard": False},
    "silhouette_iou_f0_f2": {"op": "ge", "value": 0.85, "hard": True},
    # x-drift is lax: walk-cycle contact/passing poses legitimately vary leg
    # extension by several px. Hard gate catches character size swaps only.
    "bbox_drift_x": {"op": "le", "value": 6, "hard": True},
    # y-drift tight: vertical bob is 1-2 px; >3 means the character is
    # falling/rising in-frame — a real defect.
    "bbox_drift_y": {"op": "le", "value": 3, "hard": True},
}


def _check_gate(name: str, value) -> Tuple[bool, str]:
    spec = GATES.get(name)
    if not spec:
        return True, "no-gate"
    op = spec["op"]
    target = spec["value"]
    if op == "eq":
        ok = value == target
    elif op == "ge":
        ok = value >= target
    elif op == "le":
        ok = value <= target
    elif op == "between":
        ok = target[0] <= value <= target[1]
    else:
        ok = False
    kind = "hard" if spec["hard"] else "soft"
    return ok, kind


def evaluate_sprite(img, palette_hex: List[str]) -> Dict:
    metrics = {
        "palette_fidelity": palette_fidelity(img, palette_hex),
        "alpha_crispness": alpha_crispness(img),
        "outline_coverage": outline_coverage(img, palette_hex),
        "baseline_alignment": baseline_alignment(img),
        "palette_coverage": palette_coverage(img, palette_hex),
    }
    return _build_report(metrics)


def evaluate_tileset(sheet_img, palette_hex: List[str],
                     tile_size: int, columns: int, tile_count: int) -> Dict:
    seams = sheet_per_tile_seam_diffs(sheet_img, tile_size, columns, tile_count)
    metrics = {
        "palette_fidelity": palette_fidelity(sheet_img, palette_hex),
        "alpha_crispness": alpha_crispness(sheet_img),
        "tile_seam_diff_mean": sum(seams) / len(seams) if seams else 0.0,
        "tile_seam_diffs_per_tile": seams,
    }
    return _build_report(metrics)


def evaluate_animation(sheet_img, palette_hex: List[str],
                       tile_size: int, frames: int) -> Dict:
    frame_imgs = []
    for i in range(frames):
        left = i * tile_size
        frame_imgs.append(
            sheet_img.crop((left, 0, left + tile_size, tile_size))
        )
    # silhouette_iou between contact frames (f0 vs. f2) for walk-style cycles.
    if frames >= 3:
        iou = silhouette_iou(frame_imgs[0], frame_imgs[2])
    else:
        iou = silhouette_iou(frame_imgs[0], frame_imgs[-1])
    x_drift, y_drift = bbox_drift_xy(frame_imgs)
    metrics = {
        "palette_fidelity": palette_fidelity(sheet_img, palette_hex),
        "alpha_crispness": alpha_crispness(sheet_img),
        "silhouette_iou_f0_f2": iou,
        "bbox_drift_x": x_drift,
        "bbox_drift_y": y_drift,
    }
    return _build_report(metrics)


def _build_report(metrics: Dict) -> Dict:
    results = {}
    hard_fail = False
    soft_fail = False
    for name, value in metrics.items():
        if name in GATES:
            ok, kind = _check_gate(name, value)
            results[name] = {"value": value, "pass": ok, "gate": kind}
            if not ok:
                if kind == "hard":
                    hard_fail = True
                else:
                    soft_fail = True
        else:
            results[name] = {"value": value, "pass": None, "gate": "info"}
    return {
        "metrics": results,
        "hard_fail": hard_fail,
        "soft_fail": soft_fail,
    }


def format_report(report: Dict) -> str:
    """Stdout-friendly ASCII table of report contents."""
    lines = []
    lines.append(f"{'metric':<34} {'value':>10}  {'gate':<5} {'result':<4}")
    lines.append("-" * 60)
    for name, entry in report["metrics"].items():
        v = entry["value"]
        if isinstance(v, list):
            v_str = f"[{len(v)} items]"
        elif isinstance(v, bool):
            v_str = str(v)
        elif isinstance(v, float):
            v_str = f"{v:.4f}"
        else:
            v_str = str(v)
        gate = entry["gate"]
        result = "PASS" if entry["pass"] else ("FAIL" if entry["pass"] is False else "-")
        lines.append(f"{name:<34} {v_str:>10}  {gate:<5} {result:<4}")
    status = "HARD-FAIL" if report["hard_fail"] else (
        "SOFT-FAIL" if report["soft_fail"] else "OK"
    )
    lines.append("-" * 60)
    lines.append(f"status: {status}")
    return "\n".join(lines)
