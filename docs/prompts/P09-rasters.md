# TASK P09: Raster layers — terrain, rivers, final heightmap, normal map, trees, cities, colormaps

## 1. OBJECTIVE
Generate `terrain.bmp`, `rivers.bmp`, final `heightmap.bmp`, `world_normal.bmp`, `trees.bmp`, `cities.bmp` and the `map/terrain/*.dds` colour maps for the canvas; then regenerate the `terrain` column of `definition.csv` from `terrain.bmp` — all from scripted sources, matching vanilla palettes and formats.

## 2. SCOPE & BOUNDARIES
- Active scope: `tools/rasters/**`, the listed files under `mod/map/` and `mod/map/terrain/`, the **terrain column only** of `mod/map/definition.csv` (via the generator), `data/provenance/terrain_overrides.csv`, `docs/logs/P09.md`.
- FROZEN: province pixels and IDs, coastal/continent columns, states, regions, adjacencies.

## 3. CONTEXT
- Formats and palettes (mandatory): `.claude/skills/hoi4-map-modding/references/05-rasters.md` (terrain index table, river palette, heightmap encoding, normal half-size, trees ratio, DDS).
- Vanilla palettes: read from `$HOI4_GAME_DIR/map/terrain.bmp`, `rivers.bmp`, `trees.bmp`, `cities.bmp` at runtime (palette only; never commit vanilla files). DDS dimensions/format: read the headers of the installed vanilla files.
- Inputs: DEM/bathymetry, land cover, rivers (manifest), masks (P03).

## 4. CONSTRAINTS
- Hard: exact vanilla palettes (same 256 entries) for terrain/rivers/trees/cities; 8-bit indexed output; heightmap 8-bit L; normal 24-bit W/2×H/2.
- Hard: heightmap water/land split identical to province surface classes (land ≥ 96, water ≤ 94).
- Hard: rivers 1 px wide, 4-connected, one source pixel per river main branch, tributaries joined with flow-in (index 1), river pixels only on land.
- Hard: provincial terrain = majority type of terrain.bmp within the province, then overrides from `terrain_overrides.csv` (each with reason); urban only where a 1936 city ≥ {{URBAN_THRESHOLD}} inhabitants is in the province.
- Preference: river selection by discharge/Strahler order so that the major rivers (Rhine, Danube, Vistula, Dnieper, Volga, Don, Nile, Congo, Niger, Mississippi, Missouri, Ohio, St Lawrence, Amazon, Paraná, Yangtze, Yellow, Mekong, Irrawaddy, Ganges, Indus, Tigris, Euphrates, Amur, Ob, Yenisei, Lena, Murray…) are continuous.
- Discretion: land-cover class mapping table (commit it as CSV).

## 5. DECISION RULES
- If a river pixel lands on sea/lake after rasterising → clip at the coast; the last land pixel before the mouth stays river.
- If thinning leaves a 2×2 block → skeletonise again; if a river becomes disconnected → bridge with the shortest 4-connected path along the DEM valley.
- If terrain majority is a tie → prefer the rougher type (mountain > hills > forest/jungle/marsh > desert > plains).

## 6. FAILURE MODES
1. Saving indexed images as RGB (editor or Pillow mode mistake) → `BPP`/`RIVERS_MODE` errors.
2. Heightmap coast mismatch → flooded coastal provinces.
3. Rivers of index 11 everywhere (width from wrong attribute).
4. Hand-editing definition.csv terrain.

## 7. EXECUTION WORKFLOW
INSPECT → PLAN (class mapping tables, river selection threshold → log) → EXECUTE each raster → VERIFY → REPORT (terrain type counts vs. vanilla proportions, river pixel counts per width index, override list).

## 8. VERIFICATION COMMANDS
- `python3 .claude/skills/hoi4-map-modding/scripts/validate_map.py mod --json build/validate_p09.json` → 0 ERROR; 0 `RIVERS_THICK`; `RIVERS_ON_SEA` = 0.
- `python3 tools/rasters/check.py` → palette equality with vanilla, sizes, heightmap/mask agreement, one source per river component, DDS headers match vanilla dimensions scaled to the canvas.

## 9. STOP CONDITION & CHECKPOINT
Commit `map(p09): raster layers and provincial terrain`. NEXT_ACTION = P10.
