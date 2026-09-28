# TASK P13a / P13b: Vanilla 1.19.x compatibility layer

Overwatch dispatches **compat-engineer** work units. P13a (mapping) runs after G3 and before P06; P13b (script remapping) runs after P10. Strategy: docs/PROJECT_SPEC.md §10.

## 1. OBJECTIVE
Make vanilla 1.19.x focus trees, events, decisions, history and AI work on the new map: (P13a) produce `data/compat/state_map.csv` and `data/compat/province_map.csv` so P06 can assign state IDs with vanilla IDs anchored; (P13b) a build-time generator that emits remapped overrides of every vanilla file referencing map IDs, with a coverage report that classifies 100 % of references.

## 2. SCOPE & BOUNDARIES
- Active scope: `tools/compat/**`, `tests/compat/**`, `data/compat/**`.
- FROZEN: `data/states/**` (read-only input), `mod/**` except via running the generator, all other tools.

## 3. CONTEXT
- Agent instructions: `.claude/agents/compat-engineer.md` (mapping method).
- References to scan: skill references/10-mod-integration.md §4 (folders + regex patterns).
- Inputs: vanilla files from `$HOI4_GAME_DIR`; new state polygons (skeleton pass: `build/states/skeleton.geojson`; waves: `data/states/**`), province raster (`build/pid.npy`, P05). Re-run P13a after every refinement wave so anchors follow the new states.
- Vanilla is also the "did we forget a territory?" coverage check (DEC-025): every vanilla state's geocoded area must fall inside some new state.

## 4. CONSTRAINTS
- Hard: every vanilla state ID is assigned to exactly one new state (the anchor); new states get IDs above the highest vanilla ID; no ID reused for a different place.
- Hard: vanilla text is read at build time and never committed; overrides are written into gitignored mod paths.
- Hard: coverage report `data/compat/coverage.csv` lists every reference (file, line, pattern, vanilla id, action: mapped-anchor | mapped-all-children | mapped-province | needs-human | not-applicable).
- Hard: geocoding sources are cited per vanilla state (gazetteer name + coordinates + confidence).
- Preference: territorial effects (transfer_state, add_core_of, set_state_owner, controller changes) apply to all children; presence checks (owns_state, controls_state) use all children for "owns whole region" semantics and the anchor for capital-like checks — classify each trigger type in `data/compat/trigger_semantics.csv` with a reason.

## 5. DECISION RULES
- Vanilla state whose main VP falls outside every new state (sea/rounding) → nearest new land state in the same country; log.
- Two vanilla states anchoring to the same new state → the second takes the new state with the largest overlap among the remaining children; if none, **needs-human**.
- A reference that cannot be mapped without changing gameplay meaning → needs-human with a one-line proposal; never silently delete.

## 6. FAILURE MODES
1. Anchoring by vanilla state *name* similarity instead of geography.
2. Remapping only effects and forgetting triggers/AI strategy files.
3. Committing vanilla text.

## 7. EXECUTION WORKFLOW
P13a: geocode vanilla states → anchor → child sets → province map → tests → commit. P13b: scanner → classifier → rewriter → coverage report → tests → commit.

## 8. VERIFICATION COMMANDS
- `python -m pytest -q tests/compat`
- `python tools/compat/check.py` → 100 % of references classified; 0 references to nonexistent state/province IDs in the effective mod
- full `validate_map.py mod --vanilla "$HOI4_GAME_DIR"` → 0 ERROR

## 9. STOP CONDITION & CHECKPOINT
Commit `compat(P13a|P13b): …` on the WU branch; overwatch runs the loop (validator → code-reviewer + history-auditor on geocoding → triage) and merges. `needs-human` items go to a new dated `to-check/` file for the owner.
