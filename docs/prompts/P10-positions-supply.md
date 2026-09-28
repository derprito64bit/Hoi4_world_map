# TASK P10: Positions (fully scripted, no manual nudger) and 1936 supply network

Run as `claude --agent overwatch`.

## 1. OBJECTIVE
Generate every position file (buildings, unitstacks, airports, rocketsites, weatherpositions, ambient objects) so nothing is missing at load and models sit sensibly — scripted, no manual nudger work (DEC-022) — and the 1936 supply network (`supply_nodes.txt`, `railways.txt`) from sourced historical railways.

## 2. WORK UNITS
| WU | Agent | Scope |
|---|---|---|
| P10a | researcher (per region, ≤ 6 parallel) | `data/research/railways/<region>.md` + `data/research/railways/<region>.geojson` (1936 lines with level evidence and sources) |
| P10b | pipeline-engineer | `tools/positions/**`, `tests/positions/**` (+ generated position files) |
| P10c | pipeline-engineer (after P10a) | `tools/supply/**`, `tests/supply/**` (+ generated supply_nodes/railways) |
Review: fact-checker (P10a), code-reviewer + validator + visual-qa (P10b/c).

## 3. CONTEXT
Line formats and vanilla multiplicities: skill `references/01-file-formats.md` (7-column buildings/unitstacks unchanged in 1.19.3); coordinates `x = column`, `z = H − row`, `y` = heightmap/10; supply rules `references/04-regions-adjacency-supply.md` §3–4; replicate vanilla 1.19's per-province unitstack type pattern read from `$HOI4_GAME_DIR/map/unitstacks.txt` at build time.

## 4. CONSTRAINTS
- Hard: every coordinate inside its province/state; naval_base column 7 = adjacent sea province; floating_harbor column 7 = a land province (vanilla pattern).
- Hard: per-state/province multiplicities follow vanilla 1.19 (re-measured in P00).
- Hard: railways — consecutive provinces adjacent, land provinces in states only, every line sourced, levels 1–5; supply hubs on land provinces in states, density near vanilla, always at capitals and major junctions/ports.
- Preference: positions ≥ 2 px apart; seeded rotations.

## 5. DECISION RULES
No 1936 railway GIS for a country → Tier 3 atlas tracing, `confidence=low`, listed; never invent lines. Province too small for all slots → reuse the centroid.

## 6. FAILURE MODES
z counted from the top; missing naval_base positions (crash risk); railways across sea.

## 7. VERIFICATION
- validator → 0 `RAIL_*`, `SUPPLY_*`, `BUILDINGS_*`
- `python tools/positions/check.py` (inside-province, multiplicities, full unitstack type set per province)

## 8. STOP
Merged → P13b.
