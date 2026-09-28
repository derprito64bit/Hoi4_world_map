# TASK P00b: Build the in-game experiment kit (EXP-01..EXP-09)

Overwatch dispatches this as work unit `P00b` to **pipeline-engineer** (worktree, branch `wu/P00b`), then runs the normal loop (validator → code-reviewer → triage).

## 1. OBJECTIVE
Generate nine tiny, self-contained test mods that answer the open engine questions EXP-01..EXP-09 (see both files in `to-check/`), each with a one-page instruction sheet the owner can follow without modding knowledge, so the answers can fix `PROVINCE_BUDGET`, `BBOX_MAX`, the seam-link method, the off-globe filler and state-ID rules before P01.

## 2. SCOPE & BOUNDARIES
- Active scope: `tools/experiments/**`, `tests/experiments/**`. Output mods go to `build/experiments/EXP-xx/` (gitignored) plus a launcher `.mod` file written by an install script into `$HOI4_USER_DIR/mod/` **only when the owner runs** `python tools/experiments/install.py EXP-xx`.
- FROZEN: everything else; the real map pipeline does not exist yet — do not start it.

## 3. CONTEXT
- Formats and invariants: skill references 01, 02, 04, 07. Validator: `validate_map.py`.
- Base for each experiment: copy vanilla map files from `$HOI4_GAME_DIR` **at build time into build/** (never into git), then apply the minimal change. EXP-03 and EXP-02 may generate synthetic `provinces.bmp`/`definition.csv` programmatically.

## 4. CONSTRAINTS
- Hard: each experiment changes exactly one thing relative to vanilla and says what that is.
- Hard: every generated test map passes `validate_map.py` except for the one property under test (document the expected finding).
- Hard: nothing from the game folder is committed; the install script never writes outside `$HOI4_USER_DIR/mod/`.
- Preference: EXP-03 variants 16k / 20k / 24k / 30k total provinces built by subdividing vanilla land provinces (keep vanilla states valid by assigning children to the parent's state).
- Discretion: implementation details.

## 5. EXPERIMENT DEFINITIONS
| ID | Change | Owner steps (write into `build/experiments/EXP-xx/README.txt`) | Record |
|---|---|---|---|
| EXP-01 | add 2 rows linking two non-touching sea provinces: variant A `sea` type with a sea Through, variant B empty type | start as UK, select a fleet, move it to the linked sea province | pathing yes/no per variant + error.log |
| EXP-02 | three variants: one province spread over 300 / 600 / 1,200 px width | load each | which variants load; error text |
| EXP-03 | 16k / 20k / 24k / 30k provinces | load each, note load time, play 7 days | loads? time? crash? |
| EXP-04 | provinces of 6, 7 and 8 px | load | error.log lines |
| EXP-05 | trees.bmp resized to 2:1 and to 3:1 | screenshot forests near the map edges | screenshots |
| EXP-06 | a block of the map replaced by lake provinces (simulating the off-globe filler) | pan there, move a fleet along it | rendering/pathing notes |
| EXP-07 | state IDs with one gap (e.g. renumber the last state to max+2) | load, open the state | error.log |
| EXP-08 | canvas above the community ceiling: vanilla map padded with ocean to 5632×2560 and 6144×2560 (all layers scaled consistently); plus a variant that adjusts `gfx/FX/constants.fxh` map constants if P00 found size-tied values | load each, pan to all edges, note load time | loads? rendering artefacts? error.log |
| EXP-09 | edge-look prototype on the project canvas: Equal Earth off-globe mask filled with lake provinces, heightmap 89, ocean colormap tone, `CAMERA_OUTSIDE_MAP_DISTANCE_TOP/BOTTOM` and `CAMERA_MAX_HEIGHT` variants, optional minimal shader fade (built with gfx-engineer) | screenshots at 5 zoom levels at the curved edges, the Pacific seam and the 60° S edge | screenshots + preference |

## 5b. LIMITATIONS (write into each README.txt)
Each experiment's sheet ends with "What this test cannot prove" copied from `to-check/2026-09-28_rendering-countries-canvas.md` (limitations table and EXP-08/09 rows). Results are recorded with these caveats.

## 6. FAILURE MODES
1. An experiment that changes several things (ambiguous result).
2. Committing vanilla-derived files.
3. Instructions that assume modding knowledge.

## 7. EXECUTION WORKFLOW
`git switch -c wu/P00b` → build `tools/experiments/build.py EXP-xx|all` and `install.py` → tests → run `build.py all` → validate each output (expected findings only) → commit → report.

## 8. VERIFICATION COMMANDS
- `python -m pytest -q tests/experiments`
- `python tools/experiments/build.py all --check` → each experiment reports "only the intended property differs"
- `git status --porcelain` → no files outside scope

## 9. STOP CONDITION & CHECKPOINT
Commit `tools(P00b): in-game experiment kit`. EXP-09 needs a small `gfx-engineer` WU (`P00c`) for the camera-define and shader variants; overwatch dispatches it in parallel (disjoint scope). Overwatch merges after the loop and posts to the owner: the install command per experiment and what to send back. Results go into a new dated `to-check/` file.
