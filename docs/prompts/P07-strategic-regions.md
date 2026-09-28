# TASK P07: Strategic regions and weather

Run as `claude --agent overwatch`.

## 1. OBJECTIVE
Partition every province (land, sea, lake, off-globe) into strategic regions that never cut a state, are climatically homogeneous, have sensible air/naval zone sizes and realistic monthly weather — `mod/map/strategicregions/<id>-<Name>.txt` + `strategic_region_names_l_english.yml`.

## 2. WORK UNITS
| WU | Agent | Scope |
|---|---|---|
| P07a | researcher | `data/research/climate/<region>.md` + `data/research/climate/normals.csv` (monthly min/max temperature and precipitation per candidate region centroid, with source; modern normals flagged proxy=modern) and `data/research/theatres.md` (historical naval theatre names/extents with sources) |
| P07b | pipeline-engineer (after P07a) | `tools/make_regions.py`, `tests/test_regions.py` (+ generated `mod/map/strategicregions/**`, region localisation) |
Review: fact-checker (P07a), code-reviewer + visual-qa (region previews) (P07b).

## 3. CONTEXT
Rules: skill `references/04-regions-adjacency-supply.md` §1; format `references/01-file-formats.md`; baseline sizes `references/08-vanilla-baseline.md` (vanilla 1.14: 288 regions, land median 43 / sea median 23 provinces — re-measured on 1.19 in P00). Off-globe lakes → dedicated regions (`references/06-equal-earth.md` §3).

## 4. CONSTRAINTS
- Hard: every province in exactly one region; every state inside one region; IDs 1..R.
- Hard: 12 monthly `period` blocks, `between` 0-based day.month covering the year, weights ≥ 0, southern-hemisphere seasons inverted.
- Hard: `naval_terrain` from bathymetry (< 200 m shelf → `water_shallow_sea`; fjord coasts → `water_fjords`; else `water_deep_ocean`).
- Preference: land regions 25–60 land provinces; sea regions 10–60 provinces named after historical theatres.

## 5. DECISION RULES
Region border would cut a state → move the region border. Isolated island state → surrounding sea region (vanilla precedent). Snow weight > 0 only when monthly min < 0 °C with precipitation; sandstorm only in hot deserts; arctic_water only with sea ice.

## 6. FAILURE MODES
One weather template everywhere; regions straddling the seam; unassigned lake/off-globe provinces.

## 7. VERIFICATION
- validator → 0 `SR_*`, 0 `STATE_CROSSES_REGION`, 0 `SR_NO_WEATHER`
- `python tools/make_regions.py --check` (12 periods; all days covered; July colder than January for centroids south of 23° S)

## 8. STOP
Merged → P08. Waves: re-run after each P04-W/P05b split (regions follow states).
