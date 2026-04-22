# Tiled File Format Cheatsheet

Tiled (mapeditor.org) supports two interchangeable formats: **TSX** (tileset XML) + **TMX** (tilemap XML), or the JSON variants **TSJ** + **TMJ**. This skill emits TSX for tilesets (Tiled's canonical save format) and TMJ for example tilemaps (faster to parse, easier for game engines).

## TSX — Tileset

Minimum valid TSX for a 32x32 grid sheet with 16 tiles in 4 columns:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<tileset version="1.10" tiledversion="1.11.0" name="overworld"
         tilewidth="32" tileheight="32" tilecount="16" columns="4"
         spacing="0" margin="0">
  <image source="overworld.png" width="128" height="128"/>
  <tile id="0">
    <properties>
      <property name="name" value="grass"/>
    </properties>
  </tile>
  <tile id="1">
    <properties>
      <property name="name" value="dirt"/>
    </properties>
  </tile>
</tileset>
```

### Key attrs

| Attr          | Meaning                                   |
|---------------|-------------------------------------------|
| `tilewidth`   | Tile pixel width                          |
| `tileheight`  | Tile pixel height                         |
| `tilecount`   | Total tile count (columns × rows)         |
| `columns`     | Grid columns                              |
| `spacing`     | Pixels between adjacent tiles (0 here)    |
| `margin`      | Pixels around sheet edge (0 here)         |

### `<image>` element

`source` is relative to the **TSX file's location**, not the cwd. Keep TSX + PNG in the same directory.

### Animation

Inside a `<tile id="N">` block:

```xml
<animation>
  <frame tileid="0" duration="120"/>
  <frame tileid="1" duration="120"/>
  <frame tileid="2" duration="120"/>
  <frame tileid="3" duration="120"/>
</animation>
```

When the tile is painted on a map, Tiled cycles through frame tile ids at the given per-frame duration (ms).

## TMJ — Tilemap (JSON)

Minimum TMJ referencing an external TSX:

```json
{
  "compressionlevel": -1,
  "height": 10,
  "width": 10,
  "infinite": false,
  "orientation": "orthogonal",
  "renderorder": "right-down",
  "tiledversion": "1.11.0",
  "version": "1.10",
  "tileheight": 32,
  "tilewidth": 32,
  "type": "map",
  "nextlayerid": 2,
  "nextobjectid": 1,
  "tilesets": [
    {"firstgid": 1, "source": "overworld.tsx"}
  ],
  "layers": [
    {
      "data": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, /* ... 100 total */ ],
      "height": 10,
      "width": 10,
      "id": 1,
      "name": "Tile Layer 1",
      "opacity": 1,
      "type": "tilelayer",
      "visible": true,
      "x": 0,
      "y": 0
    }
  ]
}
```

Note: in TMJ the `data` array uses **global tile ids** (gid), which are offset by `firstgid`. Tile id 0 in the TSX becomes gid 1 in the TMJ when `firstgid=1`. Gid 0 means "empty".

## Engine Notes

| Engine        | Import path                          | Gotchas                                           |
|---------------|--------------------------------------|---------------------------------------------------|
| Godot 4       | `vnen/godot-tiled-importer` addon    | Maps TSX → TileSet resource; custom props preserved |
| Unity         | `SuperTiled2Unity` package           | Reads TMX/TMJ + TSX directly                      |
| Phaser 3      | `load.tilemapTiledJSON` / `load.image` | Use TMJ; reference TSX image via separate `load.image` |
| LDtk          | Separate format — use LDtk tools     | MVP does not export LDtk; re-import from TSX if needed |

## Pixel Alignment

Common tile dimensions: 8, 16, 24, 32, 48, 64. 32 dominates top-down 2D; 16 dominates retro. No power-of-two requirement in modern Tiled or GPUs — it's convention.

## Troubleshooting

- Tileset renders as solid magenta/pink in Tiled → image path mismatch; check `<image source>` is relative to the TSX file.
- Animation doesn't play → Tiled's map view only animates during "View → Show Tile Animations"; on export, game engine must re-implement animation playback (the `<animation>` block is metadata, not a runtime).
- Tiles show tearing/bleeding at runtime → add `spacing=2, margin=2` and 1px extrude bleed to the sheet (MVP skips this; add in v2).
