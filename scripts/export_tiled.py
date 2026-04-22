"""Tiled map editor exporters (TSX tileset, TMJ tilemap).

TSX (XML) and TMJ (JSON) formats reference:
- https://doc.mapeditor.org/en/stable/reference/tmx-map-format/
- https://doc.mapeditor.org/en/stable/reference/json-map-format/

Design:
- Uniform grid, spacing=0, margin=0 (keep MVP simple).
- Per-tile <properties> carries a "name" for each tile.
- Animations declared on tile id=0 referencing subsequent tile ids.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

TILED_VERSION = "1.10"
TILED_EDITOR_VERSION = "1.11.0"


@dataclass
class AnimationFrame:
    tile_id: int
    duration_ms: int


@dataclass
class TileEntry:
    tile_id: int
    name: str | None = None
    animation: list[AnimationFrame] = field(default_factory=list)


@dataclass
class Tileset:
    name: str
    tile_size: int
    columns: int
    tile_count: int
    image_filename: str
    image_width: int
    image_height: int
    tiles: list[TileEntry] = field(default_factory=list)

    def rows(self) -> int:
        return (self.tile_count + self.columns - 1) // self.columns


def validate_tileset(ts: Tileset) -> None:
    rows = ts.rows()
    expected_w = ts.columns * ts.tile_size
    expected_h = rows * ts.tile_size
    if ts.image_width != expected_w or ts.image_height != expected_h:
        raise ValueError(
            f"Tileset image dims mismatch: image={ts.image_width}x{ts.image_height}, "
            f"expected {expected_w}x{expected_h} "
            f"(columns={ts.columns}, rows={rows}, tile_size={ts.tile_size})"
        )
    seen_ids = {t.tile_id for t in ts.tiles}
    if len(seen_ids) != len(ts.tiles):
        raise ValueError("Duplicate tile ids in tileset entries")
    for t in ts.tiles:
        if not (0 <= t.tile_id < ts.tile_count):
            raise ValueError(f"Tile id {t.tile_id} out of range 0..{ts.tile_count - 1}")


def build_tsx_tree(ts: Tileset) -> ET.ElementTree:
    validate_tileset(ts)

    tileset_el = ET.Element(
        "tileset",
        {
            "version": TILED_VERSION,
            "tiledversion": TILED_EDITOR_VERSION,
            "name": ts.name,
            "tilewidth": str(ts.tile_size),
            "tileheight": str(ts.tile_size),
            "tilecount": str(ts.tile_count),
            "columns": str(ts.columns),
            "spacing": "0",
            "margin": "0",
        },
    )
    ET.SubElement(
        tileset_el,
        "image",
        {
            "source": ts.image_filename,
            "width": str(ts.image_width),
            "height": str(ts.image_height),
        },
    )

    for entry in sorted(ts.tiles, key=lambda t: t.tile_id):
        if not entry.name and not entry.animation:
            continue
        tile_el = ET.SubElement(tileset_el, "tile", {"id": str(entry.tile_id)})
        if entry.name:
            props = ET.SubElement(tile_el, "properties")
            ET.SubElement(
                props,
                "property",
                {"name": "name", "value": entry.name},
            )
        if entry.animation:
            anim_el = ET.SubElement(tile_el, "animation")
            for frame in entry.animation:
                ET.SubElement(
                    anim_el,
                    "frame",
                    {"tileid": str(frame.tile_id), "duration": str(frame.duration_ms)},
                )

    ET.indent(tileset_el, space="  ")
    return ET.ElementTree(tileset_el)


def write_tsx(ts: Tileset, path: Path) -> None:
    tree = build_tsx_tree(ts)
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(path, encoding="UTF-8", xml_declaration=True)


def build_tmj_example(
    ts: Tileset,
    tsx_filename: str,
    map_width_tiles: int = 10,
    map_height_tiles: int = 10,
) -> dict:
    """Build a minimal TMJ map referencing the external TSX.

    Creates one layer filled with tile id 1 (first tile in tileset; TMJ uses
    firstgid-offset ids, so first tile = firstgid). Demonstrates the tileset
    rendering without requiring authoring in Tiled.
    """
    validate_tileset(ts)

    layer_data = [1] * (map_width_tiles * map_height_tiles)

    return {
        "compressionlevel": -1,
        "height": map_height_tiles,
        "infinite": False,
        "layers": [
            {
                "data": layer_data,
                "height": map_height_tiles,
                "id": 1,
                "name": "Tile Layer 1",
                "opacity": 1,
                "type": "tilelayer",
                "visible": True,
                "width": map_width_tiles,
                "x": 0,
                "y": 0,
            }
        ],
        "nextlayerid": 2,
        "nextobjectid": 1,
        "orientation": "orthogonal",
        "renderorder": "right-down",
        "tiledversion": TILED_EDITOR_VERSION,
        "tileheight": ts.tile_size,
        "tilesets": [
            {
                "firstgid": 1,
                "source": tsx_filename,
            }
        ],
        "tilewidth": ts.tile_size,
        "type": "map",
        "version": "1.10",
        "width": map_width_tiles,
    }


def write_tmj(tmj: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tmj, indent=2))
