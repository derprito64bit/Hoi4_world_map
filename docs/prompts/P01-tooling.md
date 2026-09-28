# TASK P01: Tooling — params, shared helpers, build runner, preview and provenance tools

Run as `claude --agent overwatch`. Overwatch creates the work units below, dispatches them and runs the loop in `docs/AGENT_SYSTEM.md` §3.

## 1. OBJECTIVE
Give every later phase one reproducible pipeline: a single parameter file, shared I/O helpers, a build runner that stops on failure, a preview renderer (visual-qa depends on it), a provenance checker and an asset-copy step — tested on Windows and Linux.

## 2. WORK UNITS
| WU | Agent | Scope (globs it may write) |
|---|---|---|
| P01a | pipeline-engineer | `tools/params.py`, `tools/common.py`, `tools/build_all.py`, `tools/copy_assets.py`, `tests/test_common.py`, `tests/test_build_all.py`, `requirements.txt`, `.gitignore` |
| P01b | pipeline-engineer (after P01a merges) | `tools/preview.py`, `tools/check_provenance.py`, `tests/test_preview.py`, `tests/test_provenance.py`, `data/README.md` (provenance CSV schemas live in `check_provenance.py`; state-builders create the CSVs) |
FROZEN: `.claude/**`, `docs/PROJECT_SPEC.md`, `docs/prompts/**`, `mod/**` (generated only), `assets/**`.

## 3. CONTEXT
- Parameters (single source of truth): `docs/PROJECT_SPEC.md` §2–3 and §12 (canvas 5120×2304, lon0 10.9, lat −60..90, 1936-01-01, overlay dates, budgets, `BBOX_MAX` 250/180, density weights, `A_base` 200, `A_min` 30).
- Projection: import `ee_project.Canvas` from `.claude/skills/hoi4-map-modding/scripts/` (add that path in `tools/common.py`); never copy its maths.
- Layout: skill `references/10-mod-integration.md` §1; provenance schema `references/03-states.md` §3.4.

## 4. CONSTRAINTS
- Hard: Python ≥ 3.11 + pinned `numpy pillow scipy shapely pyproj pytest` in `requirements.txt`; no GDAL/QGIS (propose in the log if ever needed).
- Hard: every parameter lives in `tools/params.py`; a test diffs it against the spec §2 table so they cannot drift.
- Hard: `build_all.py`: ordered step registry, `--list`, `--from`, `--only`, `--skeleton` (PROJECT_SPEC §12 skeleton passes), stops at the first non-zero exit, runs `validate_map.py` last with the spec's bbox limits and `--vanilla "$HOI4_GAME_DIR"`.
- Hard: `copy_assets.py` copies `assets/**` into `mod/` and fails if an asset path collides with a generated file.
- Hard: `preview.py <layer> [--region NAME | --bbox lon0,lat0,lon1,lat1] [--overlay geojson] --out PNG` for layers mask, provinces, states, regions, rivers, terrain, heightmap, seam (left and right edges side by side), offglobe; named regions cover visual-qa's standard sweep (`.claude/agents/visual-qa.md`).
- Hard: BMP writers for 24-bit RGB, 8-bit indexed (explicit palette), 8-bit L; header test asserts 40-byte DIB, compression 0.
- Hard: `pathlib` only; env vars `HOI4_GAME_DIR`, `HOI4_USER_DIR`, `HOI4_WORKSHOP_DIR`.

## 5. DECISION RULES
- Spec value ambiguous → use it as written, add `# SPEC-AMBIGUOUS` + a log line; never invent.
- `mod/map` missing → `build_all.py --list` works and the validator step reports "skipped (no map)".

## 6. FAILURE MODES
Duplicated projection code; magic numbers outside params; a runner that swallows errors; a preview that flips rows (row 0 = north).

## 7. VERIFICATION
- `python -m pytest -q tests/` → pass (BMP round-trips, params-vs-spec diff, preview smoke test on a synthetic 512×256 map)
- `python tools/build_all.py --list`
- `python tools/check_provenance.py` → exit 0 on the empty set
- `python .claude/agentops/wu_check.py diff P01a --head wu/P01a` (and P01b) → 0 outside scope

## 8. STOP
Both WUs merged → `docs/logs/P01.md` (NEXT_ACTION = P02). No owner gate.
