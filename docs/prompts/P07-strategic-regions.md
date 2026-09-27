# TASK P07: Strategic regions and weather

> **Revision pending (2026-09-27):** written before the owner's decisions (4608×2048 canvas with 60° S crop, 1.19.x, vanilla compatibility, border overlay, agent fleet). The spec and agent files are authoritative where they differ; this prompt will be refreshed and sent in chat before its phase runs.

## 1. OBJECTIVE
Partition every province (land, sea, lake, off-globe) into strategic regions that never cut a state, have homogeneous climate, sensible air/naval zone sizes and realistic monthly weather, written as `mod/map/strategicregions/<id>-<Name>.txt` plus `strategic_region_names_l_english.yml`.

## 2. SCOPE & BOUNDARIES
- Active scope: `tools/make_regions.py`, `data/regions/*.csv` (climate inputs + sources), `mod/map/strategicregions/**`, `mod/localisation/english/strategic_region_names_l_english.yml`, `docs/logs/P07.md`.
- FROZEN: provinces, definitions, states (P06), adjacencies (P08), weatherpositions (P10).

## 3. CONTEXT
- Rules: `.claude/skills/hoi4-map-modding/references/04-regions-adjacency-supply.md` §1; format `references/01-file-formats.md` (strategic region block); baseline sizes `references/08-vanilla-baseline.md` (288 regions; land median 43, sea median 23).
- Off-globe lake provinces go into dedicated regions (`references/06-equal-earth.md` §3).

## 4. CONSTRAINTS
- Hard: every province in exactly one region; every state entirely inside one region; ids 1..R contiguous.
- Hard: 12 monthly `period` blocks per region with `between` 0-based day.month ranges covering the year; weights ≥ 0; southern-hemisphere seasons inverted from the northern template.
- Hard: `naval_terrain` on sea regions from bathymetry (shelf < 200 m → `water_shallow_sea`; fjord coasts → `water_fjords`; else `water_deep_ocean`).
- Preference: land regions 25–60 land provinces; sea regions 10–60 provinces following historical naval theatre names (Western Approaches, Bay of Biscay, Coral Sea…).
- Discretion: clustering algorithm (e.g. region-growing on state adjacency graph with climate-distance penalty).

## 5. DECISION RULES
- If a candidate region would cut a state → move the region border to the state border.
- If a single island state sits far out at sea with no nearby land region → place it in the surrounding sea region (vanilla precedent).
- If climate data for a region is modern-only → use it, mark `proxy=modern` in the CSV.
- If temperature/precipitation implies snow (< 0 °C monthly mean min and precipitation) → snow weight > 0; sandstorm only for hot deserts (BWh); arctic_water only where sea ice occurs that month.

## 6. FAILURE MODES
1. Copying one weather template everywhere.
2. Regions crossing the seam without the P08 seam links (split them at the seam instead).
3. Leaving off-globe or lake provinces unassigned.

## 7. EXECUTION WORKFLOW
INSPECT (G4 audit passed) → PLAN (region count target and theatre list in log) → EXECUTE → VERIFY → REPORT (size histograms vs. vanilla, climate sources, proxy count).

## 8. VERIFICATION COMMANDS
- `python3 .claude/skills/hoi4-map-modding/scripts/validate_map.py mod --json build/validate_p07.json` → 0 ERROR for `SR_*` and `STATE_CROSSES_REGION`; 0 `SR_NO_WEATHER`.
- `python3 tools/make_regions.py --check` → 12 periods each, coverage of all days, southern-hemisphere seasonality test (July colder than January for regions with centroid lat < −23°).

## 9. STOP CONDITION & CHECKPOINT
Commit `map(p07): strategic regions and weather`. NEXT_ACTION = P08.
