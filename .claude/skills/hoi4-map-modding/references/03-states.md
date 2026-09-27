# 03 — States: creation, shaping, splitting, merging, accuracy

## 1. What a state is
A state is the unit of ownership, cores, industry (building slots), manpower,
resources, supply and peace deals. It is a set of **land** provinces (plus
optionally lakes) inside **one** strategic region. Vanilla: 969 states,
provinces per state p10 2 / median 9 / p90 21 / max 70; 66 single-province
states; 17 `impassable = yes` states (Sahara, Amazon, Himalaya-type).

## 2. Field semantics and how to set each one
| Field | Rule |
|---|---|
| `id` | 1..S contiguous. File `<id>-<Name>.txt`. Never reuse a deleted id for a different place in the same release; compact ids only in a dedicated renumber commit. |
| `name` | `"STATE_<id>"` + localisation. Name = the historical name at the start date (e.g. "Königsberg", "Bombay Presidency"), not today's. |
| `manpower` | **Total population** of the state at the start date (vanilla median 889,962, max 52,963,300). Source: census nearest the start date; if only a country total exists, distribute by a gridded population dataset (HYDE / GPW backcast) share. Record method in provenance. |
| `state_category` | From population + urbanisation (table below). Category sets building slots. |
| `resources` | Only where a documented deposit was *producing or known* by the start date. Scale so global totals stay near vanilla (steel 2,514, aluminium 1,196, chromium 1,369, oil 1,236, rubber 1,038, tungsten 1,352 across all states). |
| `history.owner` / `add_core_of` / `controller` | Owner from the start-date political boundary dataset (CShapes 2.0 for sovereign states). Cores: current owner + historically claimed nations per design doc; never guess — mark `UNRESOLVED`. |
| `victory_points` | Province id + value. Vanilla value distribution: 1 (534), 3 (207), 5 (181), 2 (79), 10 (99), 15 (33), 20 (33), 25 (7), 30 (15), 40 (5), 50 (5). Capitals of great powers 30–50; national capitals 10–30; major cities 3–10; towns 1–2. The VP province must be the province containing the city's true location. |
| `buildings` | `infrastructure` 0–5 (vanilla: 0 ×11, 1 ×221, 2 ×383, 3 ×273, 4 ×67, 5 ×1); factories ≤ slots; `N = { naval_base = k }` only on coastal province N. |
| `impassable = yes` | Only for genuinely impassable terrain states (deserts, rainforest cores, high mountain massifs). Combine with `force_link_ownership_to` if a neighbour should own it automatically. |
| `local_supplies` | 0.0 default. |

Category thresholds (starting point; tune with the vanilla distribution: rural 272, town 196, pastoral 144, city 113, wasteland 64, large_city 41, small_island 40, large_town 32, tiny_island 24, enclave 18, metropolis 17, megalopolis 8):
| Condition (start-date) | Category |
|---|---|
| uninhabited or < 5 inh/km² and no city > 20k | wasteland (0 slots) |
| island state, pop < 50k | tiny_island (0) · < 500k small_island (1) |
| enclave/exclave micro-territory (e.g. treaty ports) | enclave (0) |
| predominantly herding/sparse, < 25 inh/km² | pastoral (1) |
| agricultural, largest city < 100k | rural (2) |
| largest city 100k–250k | town (4) · 250k–500k large_town (5) |
| 500k–1M | city (6) · 1M–2M large_city (8) · 2M–5M metropolis (10) · > 5M megalopolis (12) |

## 3. Shaping states accurately — the method
### 3.1 Evidence hierarchy for a boundary (claim-specific)
- **Tier 1**: the start-date administrative boundary from an authoritative historical GIS (national historical GIS projects, MPIDR Population History GIS for Europe, Newberry Atlas of Historical County Boundaries for the US, CShapes 2.0 for sovereign borders), or official gazetteers/statutes defining the unit.
- **Tier 2**: modern admin-1/admin-2 boundaries (GADM, Natural Earth admin-1, geoBoundaries) **only where Tier 1 confirms the unit did not change** between the start date and today.
- **Tier 3**: historical atlases (scanned maps), encyclopaedic articles describing the unit.
- **Tier 4**: other mods' maps, wikis, forum posts — leads only, never adopted as a boundary.
Rule: a Tier 4 lead may tell you *where to look*; the committed geometry must cite Tier 1–3.

### 3.2 Choosing which unit becomes a state
1. Start from the start-date first-level subdivision of each sovereign country (province, governorate, oblast, state, presidency, colony).
2. **Split** a unit when any of: its province count at the target density exceeds 25; it spans two strategic regions that must stay separate (a mountain barrier, a front line); it contains two major cities (both ≥ VP 10) that historically were separate administrative seats; it mixes coastal and deep-interior areas across > 600 km. Split along **second-level** subdivision borders (districts, counties, okrugs) — never along an invented line.
3. **Merge** units when a unit would have < 2 provinces and its neighbours inside the same first-level parent are also < 2 provinces — merge along the parent's border. Never merge across a sovereign border at the start date.
4. Colonies/protectorates follow the colonial administrative divisions of the start date.
5. Keep the 1936 sovereign border as a state border everywhere, including disputed areas (put disputed area in its own state so either side can own it).
6. Record every split/merge in `data/provenance/states.csv` (schema below).

### 3.3 Geometry pipeline
1. Load the boundary polygons (Tier 1–2) → reproject lon/lat to the canvas (`ee_project.Canvas.to_pixel`).
2. Clip to the land mask; snap to coastlines (do not let a state polygon leak into sea).
3. Rasterise each state polygon to a state-id raster (every land pixel gets exactly one state; resolve gaps/overlaps by nearest polygon; log pixels resolved this way — > 0.5 % of a state's area → investigate).
4. Generate provinces inside each state (02-provinces.md §5), so state borders coincide with province borders by construction.
5. Tiny enclaves/exclaves smaller than A_min: if historically significant (e.g. Kaliningrad is not tiny; Walvis Bay, Hong Kong New Territories, Macau, Gibraltar, Danzig are) → own province/state enlarged to ≥ 12 px and logged; else merge into the surrounding state and log.

### 3.4 Provenance record (data/provenance/states.csv, one row per state)
`state_id,name,start_date_unit,parent_country_1936,source_tier,source_name,source_url_or_citation,source_feature_id,operation(created|split|merged|adjusted),parent_units,confidence(high|medium|low),notes`
Confidence `low` or `UNRESOLVED` states are listed in the phase report; a state without a row is a failed invariant.

## 4. Procedures on an existing map
### 4.1 Split state S into S and T (T = new id S_max+1)
1. Choose the provinces for T (a connected subset; both halves ≥ 1 province; neither crosses a region border).
2. Create `history/states/<T>-<Name>.txt` copying S's owner/cores/controller; move T's provinces out of S.
3. Recompute `manpower` for both from the population source; do not just halve.
4. Re-evaluate category, infrastructure, resources, VPs (VPs follow their province).
5. Move provincial buildings of moved provinces from S's block to T's.
6. `map/buildings.txt`: lines with state S whose coordinates fall inside T's provinces → change state id to T; add missing state-building positions for T (nudger "generate" or scripted placement inside T).
7. `airports.txt`, `rocketsites.txt`: add `T={province}`.
8. Localisation `STATE_T`. Any scripts referencing S that should now include T (focuses, decisions, events, `history/countries` capitals, OOB locations) → grep and update.
9. Validator → 0 new errors.
### 4.2 Merge T into S
Reverse of 4.1; then delete T's file, and (if T was the highest id) nothing else; otherwise **renumber the last state into T's id** (move file, update every reference) to keep ids contiguous. Grep the whole mod for the old id.
### 4.3 Move provinces between states
Same bookkeeping as 4.1 steps 3–9 for both states.
### 4.4 Create a state from unassigned land
Only if the validator reports `STATE_ORPHAN_LAND`; assign orphans to the adjacent state in the same region with the longest shared border unless provenance says otherwise.

## 5. Accuracy audit (use with docs/prompts P06)
For each state, the auditor answers with evidence: (1) is the outline traceable to a Tier 1–2 source for the start date; (2) is the owner correct at the start date; (3) is the name the start-date name; (4) is the VP city in the right province; (5) does manpower match the source ±10 %. Every claim is disconfirmed first: look for a boundary change between the start date and the source date. "No change found after checking X, Y" is reported as such — not as "no change".
