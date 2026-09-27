# TASK P04: Start-date state geometry for {{CONTINENT}} with provenance

> **Revision pending (2026-09-27):** written before the owner's decisions (4608×2048 canvas with 60° S crop, 1.19.x, vanilla compatibility, border overlay, agent fleet). The spec and agent files are authoritative where they differ; this prompt will be refreshed and sent in chat before its phase runs.

Run once per continent (`europe`, `north_america`, `south_america`, `australia` (Oceania), `africa`, `asia`, `middle_east`, `antarctica`), each in its own git worktree/branch; outputs are disjoint files.

## 1. OBJECTIVE
Produce `data/states/{{CONTINENT}}.geojson` — one polygon (multi-polygon allowed) per future state covering all land of {{CONTINENT}} at {{START_DATE}} — and `data/provenance/states_{{CONTINENT}}.csv` with one row per polygon, such that every boundary is traceable to a Tier 1–2 source for the start date and every split/merge follows the rules in the skill.

## 2. SCOPE & BOUNDARIES
- Active scope: `tools/states_geometry/{{CONTINENT}}.py`, `data/states/{{CONTINENT}}.geojson`, `data/provenance/states_{{CONTINENT}}.csv`, `docs/logs/P04-{{CONTINENT}}.md`.
- FROZEN: other continents' files, masks (P03), `mod/**`, `tools/params.py`, skill files.
- Unit of work: **polygons + provenance only**. No province generation, no state history (owners/manpower come in P06).

## 3. CONTEXT
- Method (mandatory reading): `.claude/skills/hoi4-map-modding/references/03-states.md` §2–3 (split/merge rules, evidence hierarchy, provenance schema).
- Density: `docs/PROJECT_SPEC.md` §3 (a state should hold ≥ 2 and ≤ 25 provinces at the target density; approximate provinces = area_px / A_target).
- Sovereign borders at the start date: CShapes 2.0 (Tier 1). Historical admin units: sources listed in `data/manifest.csv`.
- Canvas for area estimates: `Canvas(...).km2_per_px()` = 45.37 km²/px at 5120×2560.

## 4. CONSTRAINTS
- Hard: a polygon never crosses a start-date sovereign border (colonies count as separate units if administered separately).
- Hard: every polygon has a provenance row with `source_tier` 1 or 2; Tier 3 allowed only with `confidence=low` and an entry in `docs/OPEN_QUESTIONS.md`.
- Hard: Tier 4 (other mods, wikis, forums, vanilla HOI4 state shapes) may be used only to find leads; never copy geometry from them.
- Hard: polygons tile the continent's land mask: no gaps > 0.5 % of a polygon's area, no overlaps (report both).
- Preference: split along second-level historical units; names in the start-date form used by the administering state (with English exonym in notes).
- Discretion: order of countries processed; simplification tolerance ≤ 1 px (6.7 km).

## 5. DECISION RULES
- If a modern boundary is used (Tier 2) → you must cite why it equals the start-date boundary (a source stating no change, or a Tier 1 map of the start date overlaid with IoU ≥ 0.95). Otherwise it is Tier 3.
- If sources disagree → both go in `notes`; choose higher tier; equal tier → the one dated closest to the start date; still tied → `UNRESOLVED`, open an A2 research task (write it into OPEN_QUESTIONS).
- If a first-level unit exceeds 25 provinces at target density → split per 03-states §3.2 rule 2 along second-level units.
- If a unit is < 2 provinces and all neighbours in the same parent are also small → merge within the parent.
- If a territory is disputed/occupied at the start date → separate polygon; owner decided in P06.
- If you cannot find any Tier 1–3 source for a country → one polygon per sovereign unit, `confidence=low`, flag DATA-<ISO3>.

## 6. FAILURE MODES
1. Using today's borders for 1936 (e.g. post-1945 Poland, Soviet republics' later borders, post-colonial African borders, Indian princely states merged later).
2. Copying vanilla HOI4 state shapes.
3. States that exceed 25 provinces because splitting was skipped.
4. Provenance rows that cite a website home page instead of a specific dataset feature / map sheet.
5. Treating "not found" as "no boundary existed".

## 7. EXECUTION WORKFLOW
1. DISCOVERY: list sovereign units on {{CONTINENT}} at the start date (CShapes) and, per unit, the first-level subdivisions and the candidate sources. Write the list to the log.
2. VERIFICATION: for each unit, check each candidate source for start-date validity; actively look for a boundary change between the source date and the start date.
3. ADJUDICATION: apply split/merge rules; record decisions.
4. MUTATION: build the GeoJSON (properties: `tmp_id`, `name`, `country_1936`, `parent_unit`, `est_provinces`), write provenance rows.
5. VERIFY (below), then REPORT: number of polygons, histogram of est_provinces, list of low-confidence/UNRESOLVED items.

## 8. VERIFICATION COMMANDS
- `python3 tools/states_geometry/{{CONTINENT}}.py --check` → asserts tiling (gaps/overlaps thresholds), no sovereign-border crossing (intersect with CShapes lines buffered 1 px), est_provinces within 1..25 except flagged, every feature has a provenance row.
- `python3 tools/check_provenance.py --geometry data/states/{{CONTINENT}}.geojson`

## 9. STOP CONDITION & CHECKPOINT
Stop when checks pass or when > 10 % of polygons are UNRESOLVED (then stop early and report). Commit `data(p04-{{CONTINENT}}): start-date state geometry + provenance`. Gate G2 requires audit A1 by a different session; do not start P05.
