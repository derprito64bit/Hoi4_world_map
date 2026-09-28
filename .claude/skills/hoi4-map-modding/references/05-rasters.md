# 05 — Raster layers

All measured from vanilla 1.14.1 unless marked [C]; 1.19.3 re-measurement (P00) found the same values within a few pixels (see 08-vanilla-baseline.md). Same size as provinces.bmp unless stated.

## heightmap.bmp — 8-bit greyscale (palette of 256 greys), W×H
- Value v → height v/10 in engine units; sea level is 9.5 → **v < 95 renders as water, v ≥ 96 as land** [C].
- Vanilla: sea pixels are almost all 89; land 96–239 (mode 97–105 = lowlands); lakes 83–93.
- Build from a DEM (ETOPO/GEBCO/SRTM-derived): `v = 96 + k·log1p(elev_m/ s)` for land, clamp ≤ 250; sea = 89 (optionally 84–93 by depth, shelf lighter). Apply the same land mask as provinces.bmp so the rendered coastline matches the province coastline exactly (a land province with water-height pixels looks flooded; sea with land height shows islands that don't exist).
- Smooth with a small Gaussian (σ≈1 px) after masking, then re-clamp land ≥ 96 and sea ≤ 94.

## world_normal.bmp — 24-bit RGB (vanilla 1.14) or 32-bit (seen in a 1.19.3 mod), W/2 × H/2
Tangent-space normal map derived from the heightmap (Photoshop "Generate Normal Map", GIMP normal-map plugin, or scripted Sobel → normal) [C]. Recompute whenever the heightmap changes.

## terrain.bmp — 8-bit indexed, W×H
- The **palette index** of each pixel selects an entry of `terrain = { }` in `common/terrain/00_terrain.txt` by its `color = { idx }`; that entry gives the gameplay `type` and the ground `texture`.

| idx | vanilla entry | type | notes |
|---|---|---|---|
| 0 | terrain_0 | plains | most common land (~0.92 M px) |
| 1 | terrain_1 | forest | |
| 2 | desert_mountain | hills | |
| 3 | desert | desert | |
| 4 | terrain_4 | forest | |
| 5 | terrain_5 | plains | |
| 6 | terrain_6 | mountain | |
| 7 | terrain_7 | desert | |
| 8 | desert_hills | desert | |
| 9 | terrain_9 | marsh | |
| 10 | terrain_10 | mountain | |
| 11 | desert | mountain | |
| 12 | desert | desert | |
| 13 | forest_13 | urban | `spawn_city = yes` |
| 14 | forest_14 | lakes | |
| 15 | ocean_15 | ocean | all sea pixels (~7.16 M) |
| 16 | snow_16 | mountain | perm_snow |
| 17 | hills_blend | hills | |
| 18 | mountain_variation_sand | mountain | |
| 19 | plains_17 | plains | perm_snow |
| 20 | mountain_variation_grass | mountain | |
| 21 | jungle_18 | jungle | |
| 22 | jungle_blend_18 | jungle | |
| 27 | jungle_blend_18 | mountain | |
| 31 | desert_mountain_tops | mountain | |
- Copy vanilla's **palette** exactly (same 256 entries) so indices mean the same thing.
- Build from land-cover (e.g. ESA/MODIS classes) + slope from the DEM: slope > threshold → hills/mountain; tree cover → forest/jungle by climate zone; wetlands → marsh; bare/arid → desert; urban footprints → urban (sparingly — urban is a combat modifier).
- Province terrain in definition.csv = majority of mapped types, then apply design overrides and log them.

## rivers.bmp — 8-bit indexed, W×H
Palette (vanilla, by index):
| idx | RGB | meaning |
|---|---|---|
| 0 | 0,255,0 | river **source** (exactly one per river system's main branch) |
| 1 | 255,0,0 | **flow-in**: a tributary joins here |
| 2 | 255,252,0 | **flow-out**: a branch splits off (deltas) |
| 3 | 0,225,255 | narrowest river |
| 4 | 0,200,255 | |
| 5 | 0,150,255 | (unused in vanilla) |
| 6 | 0,100,255 | |
| 7 | 0,0,255 | |
| 8 | 0,0,225 | (unused in vanilla) |
| 9 | 0,0,200 | |
| 10 | 0,0,150 | |
| 11 | 0,0,100 | widest river |
| 254 | 122,122,122 | water background |
| 255 | 255,255,255 | land background |
- Rivers are 1 px wide, 4-connected chains; no 2×2 blocks; each river is one contiguous chain (tributaries joined with a flow-in pixel; only the main branch gets the green source) [C]. Save as 8-bit indexed with the standard 40-byte header [C].
- Gameplay: a province border is a river crossing if the line between the two province centres crosses a river pixel; width index decides river vs. large river penalties [C].
- Build from a river dataset (e.g. HydroRIVERS / Natural Earth rivers) filtered by discharge/Strahler order; width index from discharge class; skeletonise after rasterising.

## trees.bmp — 8-bit indexed, 1650×600 in vanilla (not map-sized)
Stretched over the whole map. Palette indices 3, 4, 7, 10 count as trees (default.map `tree = { 3 4 7 10 }`); vanilla also uses 2, 5, 6, 11, 28, 29 for other vegetation looks. Scale its aspect to the new canvas (5120×2304 ≈ 2.22:1 → e.g. 1650×742) — ratio assumption, EXP-05 verifies.

## cities.bmp — 8-bit indexed, W×H
Palette index → `city_group` in cities.txt (e.g. 15 western). Decorative city meshes; regenerate from the land mask with vanilla indices by region.

## map/terrain/*.dds
Colour maps (`colormap_rgb_cityemissivemask_a.dds` 2816×1024 in vanilla = W/2×H/2) and water colour maps must match the new canvas. Generate from a satellite-style base colour (e.g. derived from land cover) at W/2×H/2, DXT-compressed. Vanilla DDS dimensions are the reference; check each file's header in the installed game before writing replacements.

## Toolchain rules
- Never let an editor convert indexed images to RGB or change the palette order.
- Write BMPs with Pillow (`Image.save(..., "BMP")`) for P/L modes; verify headers with `validate_map.py`. Pillow writes 40-byte BITMAPINFOHEADERs; vanilla 1.19.3 ships terrain.bmp and trees.bmp with 124-byte BITMAPV5 headers — both header types are expected to load (validator accepts both; EXP-05 confirms in game).
- Keep generation scripts in `tools/` so every raster can be rebuilt from source data.
