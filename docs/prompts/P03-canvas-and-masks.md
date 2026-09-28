# TASK P03: Canvas, surface masks and draft heightmap (5120×2304, Equal Earth, 60° S crop)

Run as `claude --agent overwatch`. Owner gate **G1** at the end.

## 1. OBJECTIVE
Generate `build/masks/surface.npy` (uint8: 0 off-globe, 1 sea, 2 land, 3 lake) and a draft `mod/map/heightmap.bmp` whose water/land split matches the mask pixel for pixel, with logged island and strait adjustments — the base every later phase builds on.

## 2. WORK UNITS
| WU | Agent | Scope |
|---|---|---|
| P03a | researcher | `data/research/protected_features.md` — protected straits/isthmuses and significant small islands (name, lon/lat, why significant, source) |
| P03b | pipeline-engineer (after P03a) | `tools/make_masks.py`, `tools/make_heightmap.py`, `tests/test_masks.py`, `tests/test_heightmap.py` (+ generated `mod/map/heightmap.bmp`, `data/provenance/island_adjustments.csv`, `data/provenance/mask_edits.csv`) |
Review: fact-checker (P03a), code-reviewer + visual-qa (P03b).

## 3. CONTEXT
- Canvas, seam, off-globe rules: skill `references/06-equal-earth.md`; heightmap encoding `references/05-rasters.md`; island rule `references/02-provinces.md` §5 step 6 (8–10 px minimal blobs, DEC-009).
- `Canvas(5120, 2304, 10.9, lat_min=-60)` via `tools/params.py`.

## 4. CONSTRAINTS
- Hard: rasterise in canvas space after densifying edges to ≤ 0.25°; no land body straddles the seam (islands on the cut moved whole, logged).
- Hard: clean-up never removes a land body ≥ 8 px or any P03a feature; protected straits/isthmuses (at least Bosporus, Dardanelles, Gibraltar, Øresund, Kerch, Messina, Bab-el-Mandeb, Hormuz, Malacca, Sunda, Torres, Bering, the Panama and Suez isthmuses, Kra, Corinth) enforced by explicit masks.
- Hard: lakes < 12 px become land (count logged); heightmap land ≥ 96, water ≤ 94 (sea 89), off-globe 89.
- Hard: deterministic; runtime logged.

## 5. DECISION RULES
- 1-px bridge/channel not in P03a → resolve by 3×3 majority, log in `mask_edits.csv`.
- A continent's land px deviates > 3 % from the budget in `references/06-equal-earth.md` §2 (Antarctica excluded) → stop; check CRS, lon0, double wrap.

## 6. FAILURE MODES
lon0 applied twice (continents shifted 10.9°); rows flipped (check `ee_project.py point --lon 13.4 --lat 52.5` → row ≈ 333 is land near Berlin); off-globe treated as sea; mask/heightmap coast mismatch.

## 7. VERIFICATION
- `python tools/make_masks.py --check` (shape 2304×5120; classes ⊂ {0..3}; class 0 == `~Canvas.globe_mask()`; no land on class 0; no land component touching both column 0 and 5119)
- `python tools/make_heightmap.py --check` ((h ≥ 96) == (mask == 2) everywhere)
- `python tools/preview.py mask --region <each visual-qa sweep region>` → visual-qa report with 0 P0

## 8. STOP — owner gate G1
Overwatch posts the previews (Europe, Bering seam, Malay archipelago, Caribbean, curved edges, 60° S edge) and the per-continent table, then waits for the owner.
