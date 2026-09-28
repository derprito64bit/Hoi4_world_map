# TASK P09: Raster layers — terrain, dense rivers, final heightmap, normal map, trees, cities, colormaps

Run as `claude --agent overwatch`.

## 1. OBJECTIVE
Generate `terrain.bmp`, `rivers.bmp` (dense, DEC-010), final `heightmap.bmp`, `world_normal.bmp`, `trees.bmp`, `cities.bmp` and `map/terrain/*.dds` colour maps for 5120×2304, matching the 1.19 vanilla palettes and formats, then regenerate the definition.csv terrain column from terrain.bmp.

## 2. WORK UNITS
| WU | Agent | Scope |
|---|---|---|
| P09a | pipeline-engineer | `tools/rasters/terrain*`, `tools/rasters/heightmap*`, `tools/rasters/normal*`, `tests/rasters/test_terrain*` … (+ generated terrain/heightmap/normal, definition terrain column, `data/provenance/terrain_overrides.csv`) |
| P09b | pipeline-engineer | `tools/rasters/rivers*`, `tests/rasters/test_rivers*` (+ generated rivers.bmp) |
| P09c | pipeline-engineer | `tools/rasters/trees*`, `tools/rasters/cities*`, `tools/rasters/colormap*`, tests (+ generated trees/cities/DDS) |
P09a–c have disjoint scopes and may run in parallel. Review: code-reviewer, visual-qa (terrain/rivers/seam/off-globe previews), validator.

## 3. CONTEXT
Palettes, encodings, sizes: skill `references/05-rasters.md` (terrain index table; river palette 0–11/254/255; heightmap land ≥ 96, water ≤ 94; normal W/2×H/2, 24- or 32-bit; trees aspect per EXP-05; DDS sizes from P00). Read vanilla palettes and DDS headers from `$HOI4_GAME_DIR` at build time — never commit vanilla files.

## 4. CONSTRAINTS
- Hard: exact 1.19 vanilla palettes for terrain/rivers/trees/cities; 8-bit indexed; heightmap 8-bit L.
- Hard: heightmap water/land split identical to province surface classes; off-globe = water.
- Hard: rivers 1 px, 4-connected, one source pixel per main branch, tributaries joined with flow-in (1), no river pixels on sea/lake.
- Hard: provincial terrain = majority type, then logged overrides; urban only where a 1936 city ≥ threshold (from P06 attributes).
- Hard: colours at the seam continuous (column 0 ↔ 5119) in colormap, normal and heightmap.

## 5. DECISION RULES
River pixel on water → clip at the coast; 2×2 block → re-skeletonise; gap → bridge along the DEM valley. Terrain tie → rougher type.

## 6. FAILURE MODES
Indexed images saved as RGB; coast mismatch; rivers all max width; seam discontinuity; hand-edited terrain column.

## 7. VERIFICATION
- validator → 0 ERROR, `RIVERS_THICK` 0, `RIVERS_ON_SEA` 0
- `python tools/rasters/check.py` (palette equality with vanilla 1.19, sizes, heightmap/mask agreement, one source per river component, DDS headers match P00's measured formats scaled to the canvas, seam continuity)
- visual-qa: 0 P0

## 8. STOP
All merged → P10.
