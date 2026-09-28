# 07 — Validation, debugging, nudger

## 1. Gate ladder (a change is done only when every applicable rung passes)
| Rung | Command / action | Pass condition |
|---|---|---|
| V0 | `python .claude/skills/hoi4-map-modding/scripts/ee_project.py selftest` | prints `selftest ok` |
| V1 | `python .claude/skills/hoi4-map-modding/scripts/validate_map.py mod --json build/validate.json` | exit 0 (0 ERROR); WARN count ≤ previous run unless justified in the log |
| V2 | `python tools/check_provenance.py` (project script, P01) | every state id has a provenance row; no `confidence` empty |
| V3 | `git diff --stat` | only files in the task's declared scope changed |
| V4 (human, needs game) | launch with `-debug`, load the mod, open `Documents/Paradox Interactive/Hearts of Iron IV/logs/error.log` | 0 lines containing `MAP_ERROR`, `X crossing`, `TOO LARGE BOX`, `pixels`, `province`, `state` errors introduced by the change |
| V5 (human) | start each bookmark, observe 30 days at max speed | no crash; supply map mode renders; railways/ports drawn |

Container agents can run V0–V3 only. They must list V4–V5 as pending in their report — never claim them.

## 2. What validate_map.py checks (codes)
Bitmaps: `PROVINCES_BPP DIM_NOT_256 AREA_TOO_LARGE SIZE_MISMATCH BPP BMP_COMPRESSED NORMAL_SIZE MISSING_FILE`
Definitions: `DEF_COLUMNS DEF_PARSE DEF_IDS DEF_ROW0 DEF_DUP_COLOR DEF_TYPE DEF_COASTAL DEF_TERRAIN DEF_SEA_CONTINENT DEF_LAND_CONTINENT DEF_CONTINENT_RANGE`
Pixels: `BMP_UNDEFINED_COLOR DEF_NO_PIXELS PROVINCE_TOO_SMALL X_CROSSING BBOX_LARGE(warn) COASTAL_FALSE_POSITIVE COASTAL_FALSE_NEGATIVE`
Adjacencies: `ADJ_HEADER ADJ_TERMINATOR ADJ_PARSE ADJ_BAD_PROVINCE ADJ_TYPE(warn) ADJ_THROUGH ADJ_SEA_MIXED(warn) ADJ_RULE`
Regions: `SR_NO_ID SR_DUP_ID SR_NO_WEATHER(warn) SR_MISSING_PROVINCE SR_DUP_PROVINCE SR_BAD_PROVINCE`
States: `STATE_PARSE STATE_NO_ID STATE_DUP_ID STATE_CATEGORY STATE_NO_MANPOWER STATE_NO_OWNER(warn) STATE_VP_OUTSIDE STATE_BUILDING_OUTSIDE STATE_NAVAL_NOT_COASTAL STATE_IDS STATE_ORPHAN_LAND STATE_DUP_PROVINCE STATE_SEA_PROVINCE STATE_CROSSES_REGION STATE_EMPTY STATE_NONCONTIGUOUS(warn)`
Supply: `RAIL_COUNT RAIL_NOT_LAND RAIL_NO_STATE RAIL_GAP SUPPLY_NOT_LAND SUPPLY_NO_STATE`
Buildings: `BUILDINGS_BAD_STATE BUILDINGS_NAVAL_SEA`
Rivers: `RIVERS_MODE RIVERS_INDEX RIVERS_ON_SEA(warn) RIVERS_THICK(warn)`

Calibration: vanilla 1.14.1 → 9 ERROR (`STATE_VP_OUTSIDE`, vanilla's own data bugs), WARN: 1 sea province with continent 2, 32 non-contiguous states, 1,519 river pixels on sea, 4 thick river blocks. A mutation test (injected X-crossing, undefined colour, removed province, flipped coastal flag) produced the expected 6 new error codes.

Not checked (manual / in-game): weather realism, bbox exact limit, province count ceiling, DDS sizes, unitstacks completeness, localisation completeness (write a grep check per phase), nudger positions.

## 3. Debug mode and error.log (human step)
- Launch option `-debug` (Steam → Properties → Launch options). Without it, any MAP_ERROR closes the game at load [C].
- Log folder: `Documents/Paradox Interactive/Hearts of Iron IV/logs/` → `error.log`, `game.log`. Clear it before each test.
- Typical map errors [C]: "Map invalid X crossing. Please fix pixels at coords", "Province X has only Y pixels … Should have at least 8", "TOO LARGE BOX", missing definitions for bitmap colours, provinces in no state / no strategic region, naval base without position.

## 4. Nudger (in-game map position editor) [C]
- Opened from the in-game console (`nudge`) in debug mode. Edits positions for buildings (buildings.txt), unit stacks/VP markers (unitstacks.txt), weather positions, state/strategic region/supply assignment, adjacencies.
- Output goes to the **user directory** (`Documents/Paradox Interactive/Hearts of Iron IV/map/...`), not the mod. Move the files into the mod and delete them from the user directory, or they will shadow every future launch, including vanilla.
- "Generate" buttons create missing building/unit positions — the fastest way to fill buildings.txt/unitstacks.txt for a new map. Known to be unstable; save often [C].
- Scripted alternative (container-safe): place positions at province centroids / coastal edge points with the P10 generator; nudge by hand only for polish.

## 5. Regression discipline
- Store `build/validate.json` per phase; compare code counts before/after. A new ERROR code = revert.
- If two fixes in a row fail the validator for the same code, stop and write the blocker into the phase log with the failing coordinates/IDs.
