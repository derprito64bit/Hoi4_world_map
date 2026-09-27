# TASK P05: Generate provinces.bmp and definition.csv

## 1. OBJECTIVE
Generate every province of the map — land (inside state polygons), sea, lake and off-globe filler — as `mod/map/provinces.bmp` + `mod/map/definition.csv` + `mod/map/continent.txt`, plus `build/pid.npy` (province-id raster) and `build/state_raster.npy`, such that the validator reports 0 ERROR for all bitmap/definition checks and the total count is within `PROVINCE_BUDGET`.

## 2. SCOPE & BOUNDARIES
- Active scope: `tools/make_provinces.py` (+ helpers under `tools/provinces/`), `mod/map/provinces.bmp`, `mod/map/definition.csv`, `mod/map/continent.txt`, `data/provenance/province_ids.csv` (id → tmp_state_id, centroid lon/lat), `docs/logs/P05.md`.
- FROZEN: masks and heightmap (P03 — if they are wrong, stop and report), state polygons (P04), `mod/history/**`, all other `mod/map/*` files.

## 3. CONTEXT
- Algorithm & rules (mandatory): `.claude/skills/hoi4-map-modding/references/02-provinces.md` §2, §4, §5, §6.
- Off-globe fill: `references/06-equal-earth.md` §3. Seam: §4.
- Inputs: `build/masks/surface.npy`, `data/states/*.geojson`, density weights in `tools/params.py`.
- VP/port/capital seeds: from P04 notes and a city dataset (1936 population where available).

## 4. CONSTRAINTS
- Hard: no province crosses a state polygon border, the seam, or a surface-class border (land/sea/lake/off-globe).
- Hard: invariants 1–6 of SKILL.md §3; ≥ 8 px per province (target ≥ 40 px land, 12 px enlarged islands); 0 X-crossings; bbox ≤ `BBOX_MAX`.
- Hard: deterministic output (fixed RNG seed in params); running twice produces identical files (compare SHA-256).
- Hard: ID order: land (grouped by state, row-major centroid within state) → sea → lake → off-globe. Row 0 dummy.
- Hard: colours unique, never `0,0,0`, deterministic.
- Preference: province borders follow rivers/ridges where the cost surface supports it.
- Discretion: Voronoi/Dijkstra implementation details, performance tricks.

## 5. DECISION RULES
- Budget first: compute expected counts per region from masks and weights; if total > budget → scale `A_base` globally and print the table before generating. Never exceed the budget to "fit" a region.
- If a state polygon rasterises to < 8 px → it cannot become a state: merge into the neighbour in the same parent unit and log (P06 will see the change via `state_raster`), or, if historically significant, enlarge per island rule.
- If X-crossing removal oscillates > 20 iterations at one location → reassign the 2×2 block wholesale to the province with the most pixels in the 5×5 neighbourhood; log it.
- If a sea province would exceed the bbox limit → split it.
- continent.txt: vanilla 7 continents + `antarctica` appended as 8 (localise in P11); continent per land province from its state's continent.

## 6. FAILURE MODES
1. Provinces straddling state borders because provinces were generated before rasterising states.
2. Non-deterministic colours/IDs (unseeded RNG, dict ordering).
3. Sub-8-px slivers produced by the X-crossing fixer.
4. Coastal flags computed with 8-connectivity (must be 4-connected, seam-aware).
5. Sea provinces so large that ports have no dedicated adjacent sea tile.

## 7. EXECUTION WORKFLOW
1. INSPECT: G2 passed (A1 audit report in `docs/logs/`); `git status` clean.
2. PLAN: print budget table → log.
3. EXECUTE: state raster → land provinces per state → sea → lakes → off-globe → cleanup loop → IDs/colours → write BMP/CSV/continent.txt.
4. VERIFY (below).
5. REPORT: counts by type, area percentiles vs. `references/08-vanilla-baseline.md`, bbox max, number of enlarged islands/merged micro-states, runtime.

## 8. VERIFICATION COMMANDS
- `python3 .claude/skills/hoi4-map-modding/scripts/validate_map.py mod --json build/validate_p05.json` → 0 ERROR among `PROVINCES_BPP DIM_NOT_256 AREA_TOO_LARGE DEF_* BMP_UNDEFINED_COLOR DEF_NO_PIXELS PROVINCE_TOO_SMALL X_CROSSING COASTAL_*` (state/region codes will fail until P06/P07 — list them as expected).
- `python3 tools/make_provinces.py --check` → asserts no province spans two state-raster values, surface classes, or the seam; count ≤ budget.
- Run the generator twice → `sha256sum mod/map/provinces.bmp mod/map/definition.csv` identical.

## 9. STOP CONDITION & CHECKPOINT
Stop when verification passes. Commit `map(p05): provinces and definitions`. From this commit on, **province IDs are frozen**. HARD STOP at Gate G3 (agent-checkable: record the validator summary in the log).
