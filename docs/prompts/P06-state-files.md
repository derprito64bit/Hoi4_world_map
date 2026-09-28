# TASK P06: State files, countries and localisation

Run as `claude --agent overwatch`. Agent gate **G4** (history-auditor PASS) after each wave.

## 1. OBJECTIVE
Emit `mod/history/states/<id>-<Name>.txt` for every state with 1936 owner/controller/cores/claims, census manpower, derived category, VPs in the true city province, infrastructure/buildings, real 1936 resources (incl. coal), vanilla-anchored IDs (P13a), plus country history stubs for new tags and all state/VP localisation — so every `STATE_*` validator check passes and every row is fact-checked.

## 2. WORK UNITS
| WU | Agent | Scope |
|---|---|---|
| P06a | pipeline-engineer | `tools/make_states.py`, `tools/make_localisation.py`, `tests/test_states.py` (writes `mod/history/states/**`, `mod/localisation/english/state_names_l_english.yml`, `victory_points_l_english.yml` via generators) |
| P06-<ISO3> attribute WUs (same split and order as P04-W) | state-builder | `data/states/<continent>/<ISO3>_attributes.csv`, `data/provenance/states_<ISO3>.csv`, `data/research/<ISO3>/**` |
Review: fact-checker (every attribute row), history-auditor (G4 sample), code-reviewer (P06a), validator, triage.

## 3. CONTEXT
- Field rules: skill `references/03-states.md` §2 (categories, VP scale, infrastructure); formats `references/01-file-formats.md`; resources incl. **coal** (1.17+, confirm key list from `common/resources` in P00).
- State IDs: from `data/compat/state_map.csv` (P13a): every vanilla 1.19 ID anchored; new IDs above the highest vanilla ID.
- Countries: `data/countries/tags.csv` (P04-S-list), rule PROJECT_SPEC `COUNTRIES`.

## 4. CONSTRAINTS
- Hard: every land province in exactly one state; no sea province in a state; VPs/provincial buildings/naval bases only on provinces of that state; naval bases only on coastal provinces.
- Hard: manpower = census population nearest 1936 with the method recorded (census, or grid share of a census total) — never copied from vanilla.
- Hard: resources only with a cited 1936 deposit/production source; report totals per resource vs. vanilla 1.19.
- Hard: localisation UTF-8 **with BOM**, header `l_english:`.
- Hard: no other mod or vanilla HOI4 as a source for names, manpower, VPs or resources.

## 5. DECISION RULES
- City coordinate lands on water/wrong state → nearest land province of the correct state (log).
- Two VP cities in one province → one VP (higher value), log.
- Owner ambiguous (condominium, mandate, disputed) → administering power on 1936-01-01; alternatives in notes; fact-checker confirms.
- Census detail missing → grid share of the national census total (`confidence=medium`); national total missing too → `UNRESOLVED`, grid only, `confidence=low`.
- Category thresholds give an absurd result → documented override.

## 6. FAILURE MODES
Copying vanilla numbers; today's countries in 1936 (e.g. Pakistan, Israel); statuses accepted without the calibration check; VP in the wrong province; localisation without BOM.

## 7. VERIFICATION
- `python .claude/skills/hoi4-map-modding/scripts/validate_map.py mod --vanilla "$HOI4_GAME_DIR" --json build/validate_p06.json` → 0 `STATE_*` ERROR (except `STATE_CROSSES_REGION` until P07) and no new other codes
- `python tools/check_provenance.py` → 0
- localisation check: every `STATE_<id>` and `VICTORY_POINTS_<prov>` key present; BOM present
- fact-checker: 0 WRONG / UNSUPPORTED on owner, name, border rows

## 8. STOP
Skeleton pass → P07. Each wave → G4 audit PASS → rebuild downstream.
