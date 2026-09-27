# TASK P03: Canvas, land/sea/lake/off-globe masks and draft heightmap

> **Revision pending (2026-09-27):** written before the owner's decisions (4608×2048 canvas with 60° S crop, 1.19.x, vanilla compatibility, border overlay, agent fleet). The spec and agent files are authoritative where they differ; this prompt will be refreshed and sent in chat before its phase runs.

## 1. OBJECTIVE
Generate the base rasters every later phase builds on, in the Equal Earth canvas: `build/masks/surface.npy` (uint8: 0 off-globe, 1 sea, 2 land, 3 lake), a preview PNG, and a draft `mod/map/heightmap.bmp` whose water/land split matches the mask pixel-for-pixel.

## 2. SCOPE & BOUNDARIES
- Active scope: `tools/make_masks.py`, `tools/make_heightmap.py`, `build/masks/**`, `mod/map/heightmap.bmp`, `data/provenance/island_adjustments.csv`, `data/provenance/mask_edits.csv`, `docs/logs/P03.md`.
- FROZEN: `mod/map/provinces.bmp`, `definition.csv` (P05), states (P04/P06), everything else.

## 3. CONTEXT
- Canvas, seam, off-globe rules: `.claude/skills/hoi4-map-modding/references/06-equal-earth.md` (all of it).
- Heightmap encoding: `references/05-rasters.md` (heightmap section): land ≥ 96, water ≤ 94 (sea 89).
- Projection: `from ee_project import Canvas` (skill scripts dir) with `tools/params.py` values.
- Data: coastline/land/lakes (Natural Earth 10 m or better), DEM + bathymetry, per `data/manifest.csv`.

## 4. CONSTRAINTS
- Hard: rasterise in canvas space after densifying polygon edges to ≤ 0.25°; pixel centres decide membership.
- Hard: no land polygon may straddle the seam; islands on the cut are moved whole to one side and logged (06 §4).
- Hard: morphological clean-up must not delete any land body ≥ 8 px or any listed significant island; must not open or close straits/isthmuses on the protected list (Bosporus, Dardanelles, Gibraltar, Øresund, Kerch, Messina, Bab-el-Mandeb, Hormuz, Malacca, Sunda, Torres, Bering, Panama isthmus, Suez isthmus, Kra, Corinth) — protect them by explicit masks.
- Hard: lakes smaller than 12 px become land; record count.
- Preference: vectorised numpy; whole run < 10 min.
- Discretion: resampling method for the DEM (document it).

## 5. DECISION RULES
- If a 1-px-wide land bridge or water channel appears that is not on the protected list → remove it (land bridge → sea or water channel → land by majority of the 3×3 neighbourhood), log in `mask_edits.csv`.
- If a historically significant island (VP, naval base, strait endpoint, 1936 colony seat) rasterises to < 12 px → stamp a compact 12–20 px blob at its true centroid, log in `island_adjustments.csv` with source coordinates.
- If total land px per continent deviates > 3 % from `references/06-equal-earth.md` §2 → stop and investigate (wrong CRS, wrong lon0, double-wrap).
- If heightmap land pixel would be < 96 → set to 96; water pixel > 94 → set to 89.

## 6. FAILURE MODES
1. Longitude wrap bug (lon0 applied twice) → continents shifted by 10.9°.
2. Rows flipped (BMP bottom-up confusion) → check Berlin lands at row ≈ 353 from the top at lon0 10.9 (`ee_project.py point --lon 13.4 --lat 52.5`).
3. Off-globe pixels treated as sea (they must be class 0).
4. Coastline mismatch between mask and heightmap.

## 7. EXECUTION WORKFLOW
1. INSPECT: P02 manifest rows `ok`; `ee_project.py selftest`.
2. PLAN: write the protected-straits list and significant-island list (with coordinates and source) to the log before running.
3. EXECUTE masks → islands/straits fixes → heightmap.
4. VERIFY (commands below), render `build/masks/preview.png` (classes coloured) and a zoomed crop of Europe, the Bering seam, the Malay archipelago and the Caribbean.
5. REPORT per-continent land px vs. budget, counts of edits.

## 8. VERIFICATION COMMANDS
- `python3 tools/make_masks.py --check` → asserts: shape (H, W) = params; classes ⊂ {0,1,2,3}; class-0 pixels == `~Canvas.globe_mask()`; no land/lake pixel in class 0; no land component crosses column 0/W-1.
- `python3 tools/make_heightmap.py --check` → heightmap.bmp is 8-bit, W×H; `(h>=96) == (mask==2)` for every pixel; water pixels ≤ 94.
- `python3 .claude/skills/hoi4-map-modding/scripts/ee_project.py point --lon 13.4 --lat 52.5` and confirm the preview shows Berlin's land at that pixel.

## 9. STOP CONDITION & CHECKPOINT
Stop when checks pass. Commit `map(p03): equal-earth masks and draft heightmap` (commit only scripts, CSVs, heightmap.bmp; `build/` stays ignored — attach preview paths in the log). HARD STOP at Gate G1: final message lists the preview images for the owner and the per-continent table.
