# 10 — Mod packaging, replace_path, localisation, vanilla breakage

## 1. Layout of the mod inside this repo
```
mod/                         <- the actual HOI4 mod root (what the launcher loads)
  descriptor.mod
  map/ ...                   (all map files; replaces vanilla files of the same name)
  history/states/ ...
  map/strategicregions/ ...
  common/state_category/ ... (only if changed)
  localisation/english/*_l_english.yml
tools/                       <- generation scripts (python), committed
data/                        <- small derived data + provenance CSVs (raw downloads are NOT committed; see data/README.md)
build/                       <- validator reports (gitignored except summaries)
docs/                        <- spec, prompts, logs
```

## 2. descriptor.mod
```
name="Equal Earth World"
version="0.1.0"
supported_version="1.14.*"      # set to the installed game version at P00
tags={ "Map" "Alternative History" }
replace_path="history/states"
replace_path="map/strategicregions"
replace_path="map/supplyareas"
replace_path="history/units"       # only once OOBs are rewritten; see §4
```
`replace_path` makes the game ignore vanilla files in that folder. Map files in `map/` with the same name as vanilla simply override. Without `replace_path="history/states"`, vanilla state files with ids not overwritten by the mod would still load and reference nonexistent provinces → crash.

## 3. Localisation
- Files: `localisation/english/<name>_l_english.yml`, **UTF-8 with BOM**, first line `l_english:`, entries ` KEY:0 "Text"` (leading space).
- Required keys: `STATE_<id>` for every state, `VICTORY_POINTS_<province>` for every VP province, `STRATEGICREGION_<id>` for every region, each adjacency rule name, each continent name if new.
- Use `replace` subfolder (`localisation/english/replace/`) to override vanilla keys with the same name.

## 4. What else breaks when states and provinces change (total-conversion scope)
Vanilla content hard-codes state and province ids. After replacing the map, these must be rewritten, stubbed or replaced:
- `history/countries/*.txt` — `capital = <state id>`.
- `history/units/*.txt` — division `location = <province>`, naval bases, air wings `<state> = { }`.
- `common/national_focus/*`, `events/*`, `common/decisions/*`, `common/scripted_effects/*`, `common/scripted_triggers/*`, `common/on_actions/*`, `common/ai_strategy*/*`, `common/peace_conference/*`: `state = N`, `N = { ... }` state scopes, `owns_state`, `controls_state`, `transfer_state`, `province = N`.
- `common/bookmarks/*`, `common/countries/*` (colours are fine), `common/unit_leader` / characters (no ids usually).
- `map/buildings.txt`, `map/unitstacks.txt`, `map/airports.txt`, `map/rocketsites.txt`, `map/weatherpositions.txt`, `map/supply_nodes.txt`, `map/railways.txt`.
Strategy for the first playable milestone: replace_path the affected folders with minimal generic content (every country gets capital + no focus tree + no events) and re-introduce content in a later milestone (outside the map build; see docs/PROJECT_SPEC.md §9). Grep patterns for the audit: `\bstate\s*=\s*\d+`, `\b\d+\s*=\s*\{` inside `every_state`/`state` scopes, `capital\s*=\s*\d+`, `location\s*=\s*\d+`, `province\s*=\s*\d+`.

## 5. Licence hygiene
Do not commit vanilla assets (bitmaps, DDS, vanilla text). Generated data derived from public-domain/open datasets may be committed with attribution in `data/README.md`. Check each dataset's licence before use and record it (Natural Earth is public domain; GADM restricts commercial use; verify CShapes, HYDE, HydroSHEDS and every other source at download time).
