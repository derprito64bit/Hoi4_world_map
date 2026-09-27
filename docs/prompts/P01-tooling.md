# TASK P01: Repository scaffolding and build tooling

## 1. OBJECTIVE
Create the directory layout, a single build runner, shared Python helpers and the provenance checker so every later phase adds generators to one reproducible pipeline and can prove its output with deterministic commands.

## 2. SCOPE & BOUNDARIES
- Active scope: `tools/**`, `data/README.md`, `data/provenance/` (headers only), `mod/descriptor.mod` (skeleton), `.gitignore`, `requirements.txt`, `docs/logs/P01.md`.
- FROZEN: `.claude/skills/**` (use its scripts, don't modify), `docs/PROJECT_SPEC.md`, `docs/prompts/**`, `CLAUDE.md`.

## 3. CONTEXT
- G0 decisions: `docs/logs/P00.md` (owner answers appended there). Use those parameter values, not the defaults, where they differ.
- Layout: `.claude/skills/hoi4-map-modding/references/10-mod-integration.md` §1.
- Provenance schema: `references/03-states.md` §3.4.

## 4. CONSTRAINTS
- Hard: Python 3.11 standard library + `numpy pillow scipy shapely pyproj` only (pin versions in `requirements.txt`). No new heavy deps (GDAL, QGIS) — if one becomes necessary later, the phase that needs it proposes it.
- Hard: `data/raw/` and `build/` are gitignored; only small derived data and CSVs are committed.
- Hard: all parameters come from one file `tools/params.py` (canvas, lon0, start date, budgets, density weights) — no magic numbers elsewhere.
- Preference: each generator is a module with `main()` and a `--check` mode that validates without writing.
- Discretion: internal code organisation.

## 5. DECISION RULES
- If a helper already exists in the skill scripts (projection, validation) → import/call it; do not copy it.
- If a parameter is unconfirmed at G0 → use the spec default and mark it `# UNCONFIRMED` in params.py.

## 6. FAILURE MODES
1. Duplicating the projection math instead of importing `ee_project.py`.
2. Committing downloaded rasters.
3. A build runner that silently skips failed steps.

## 7. EXECUTION WORKFLOW
1. INSPECT `git status`, read P00 log.
2. CREATE: `tools/params.py`; `tools/common.py` (canvas via `ee_project.Canvas`, BMP writers for 24-bit RGB / 8-bit indexed with a given palette / 8-bit L, province-id raster load/save as `.npy`); `tools/build_all.py` (ordered steps registry, `--from`/`--only`, stops on first non-zero exit, runs the validator at the end); `tools/check_provenance.py` (every state id in `mod/history/states` has exactly one row in `data/provenance/states*.csv`, required columns non-empty, `source_tier` ∈ {1,2,3}); `tests/test_common.py` (BMP round-trips for each mode; header bytes: 40-byte DIB, bpp 24/8, compression 0).
3. `mod/descriptor.mod` skeleton per 10-mod-integration.md §2 with version from G0.
4. `data/README.md`: table of datasets (filled in P02), licence column, "raw data not committed" note.

## 8. VERIFICATION COMMANDS
- `python3 -m pytest -q tests/` → all pass
- `python3 tools/build_all.py --list` → shows registered steps (none yet besides validate)
- `python3 tools/check_provenance.py` → exit 0 on the empty state set
- `git diff --stat` → only Active scope

## 9. STOP CONDITION & CHECKPOINT
Stop when all verification passes. Commit `tools(p01): scaffolding, params, build runner, provenance checker`. Log `docs/logs/P01.md` with NEXT_ACTION = P02.
