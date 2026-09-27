# TASK P10: Positions (buildings, unitstacks, airports, rocketsites, weather) and supply (nodes, railways)

## 1. OBJECTIVE
Generate every position file the engine needs so that nothing is missing at load and building/unit models appear in sensible places, and create the start-date supply network (`supply_nodes.txt`, `railways.txt`) from historical sources.

## 2. SCOPE & BOUNDARIES
- Active scope: `tools/positions/**`, `tools/supply/**`, `data/railways/*` (curated inputs + sources), `mod/map/buildings.txt`, `mod/map/unitstacks.txt`, `mod/map/airports.txt`, `mod/map/rocketsites.txt`, `mod/map/weatherpositions.txt`, `mod/map/supply_nodes.txt`, `mod/map/railways.txt`, `mod/map/ambient_object.txt` (emptied or regenerated), `docs/logs/P10.md`.
- FROZEN: all bitmaps, definitions, states, regions, adjacencies.

## 3. CONTEXT
- Line formats and vanilla multiplicities: `.claude/skills/hoi4-map-modding/references/01-file-formats.md` (buildings, unitstacks, weatherpositions, airports, rocketsites, supply_nodes, railways). Coordinates: `x = column`, `z = H − row`, `y` = heightmap value / 10 at that pixel (vanilla ~9.5 on water, 10–12 on lowland).
- Supply rules: `references/04-regions-adjacency-supply.md` §3–4. Vanilla: 713 hubs / 969 states; railway levels 1–4.
- unitstacks types: vanilla uses types 0–38 per province (see `references/01-file-formats.md`); replicate vanilla's per-type pattern (land provinces get the land set, sea provinces the naval set) by inspecting a vanilla province of each kind in `$HOI4_GAME_DIR/map/unitstacks.txt`.

## 4. CONSTRAINTS
- Hard: every coordinate lies inside the province/state it belongs to (point-in-raster check); naval_base column 7 = an adjacent sea province; floating_harbor column 7 = a land province id (vanilla pattern; copy it).
- Hard: per-state multiplicities follow vanilla (6 arms_factory, 6 industrial_complex, 3 anti_air, 1 each air_base/fuel_silo/nuclear_reactor/rocket_site/synthetic_refinery, radar_station in ~95 % of states (vanilla 921/969); per land province bunker + supply_node; per coastal province naval_base + coastal_bunker + floating_harbor; dockyard where vanilla-like).
- Hard: railways: consecutive provinces adjacent; only land provinces in states; each line cites a source segment; levels 1–5.
- Hard: supply hubs on land provinces in states, preferably on railways; density near vanilla (713 hubs / 969 states ≈ 0.74 per state), always at country capitals and major rail junctions/ports.
- Preference: positions spaced ≥ 2 px apart within a province; rotation random but seeded.
- Discretion: exact placement heuristics.

## 5. DECISION RULES
- If a 1936 railway dataset is unavailable for a country → Tier 3 atlas tracing, `confidence=low`, listed in the log; never invent lines to "connect" hubs.
- If a hub province has no railway → allowed (ports, remote capitals) but listed.
- If a province is too small for all unitstack positions without overlap → reuse the centroid for extra slots (vanilla does this for tiny provinces).

## 6. FAILURE MODES
1. z computed from the top (models appear mirrored north–south).
2. Missing naval_base positions → crash when a port is built [C].
3. Railways through sea provinces.

## 7. EXECUTION WORKFLOW
INSPECT → PLAN (sources for railways; hub list) → EXECUTE → VERIFY → REPORT (line counts per building type vs. expected formula; railway km by level; hub count).

## 8. VERIFICATION COMMANDS
- `python3 .claude/skills/hoi4-map-modding/scripts/validate_map.py mod --json build/validate_p10.json` → 0 ERROR (`RAIL_*`, `SUPPLY_*`, `BUILDINGS_*`).
- `python3 tools/positions/check.py` → every coordinate inside its province/state; counts match multiplicity formulas; every province has the vanilla unitstack type set.

## 9. STOP CONDITION & CHECKPOINT
Commit `map(p10): positions, supply hubs, railways`. NEXT_ACTION = P11. Note for the owner: in-game nudger polish is optional after G6.
