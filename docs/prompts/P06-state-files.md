# TASK P06: Write history/states files (ownership, category, manpower, VPs, buildings, resources)

> **Revision pending (2026-09-27):** written before the owner's decisions (4608×2048 canvas with 60° S crop, 1.19.x, vanilla compatibility, border overlay, agent fleet). The spec and agent files are authoritative where they differ; this prompt will be refreshed and sent in chat before its phase runs.

## 1. OBJECTIVE
Emit one `mod/history/states/<id>-<Name>.txt` per state polygon with correct start-date owner/cores, population-based manpower, derived state_category, VPs in the true city province, infrastructure/building levels and resources — plus `state_names_l_english.yml` and `victory_points_l_english.yml` — so that all `STATE_*` validator checks pass and every state has a complete provenance row.

## 2. SCOPE & BOUNDARIES
- Active scope: `tools/make_states.py`, `data/states_attributes/*.csv` (manpower, owners, cores, VPs, resources, infrastructure inputs with source columns), `mod/history/states/**`, `mod/localisation/english/state_names_l_english.yml`, `mod/localisation/english/victory_points_l_english.yml`, `data/provenance/states.csv` (merged from per-continent files + final `state_id`), `docs/logs/P06.md`.
- FROZEN: `mod/map/provinces.bmp`, `definition.csv` (IDs frozen), polygons (P04 — report defects, don't fix), strategic regions (P07), `common/state_category` (use vanilla categories).

## 3. CONTEXT
- Field rules, category thresholds, VP value scale, infrastructure distribution: `.claude/skills/hoi4-map-modding/references/03-states.md` §2.
- Formats: `references/01-file-formats.md` (state file, localisation with UTF-8 BOM).
- Calibration: `references/08-vanilla-baseline.md` (manpower median 0.89 M; VP distribution; resource totals).
- Inputs: `build/state_raster.npy`, `build/pid.npy`, `data/provenance/province_ids.csv`, P04 polygons & provenance, population datasets from the manifest.

## 4. CONSTRAINTS
- Hard: state ids 1..S contiguous, ordered by continent then country tag then name (stable). File names ASCII (transliterate), `<id>-<Name>.txt`.
- Hard: every land province in exactly one state; no sea province; VPs, provincial buildings and naval bases only on provinces of that state; naval bases only on coastal provinces.
- Hard: `owner` from start-date sovereignty/administration; country tags from a single `data/countries_1936.csv` (tag, name, source). If a needed country tag is not decided yet, create the row with `status=proposed` — do not invent tags inline.
- Hard: manpower = start-date population with a documented method (census or grid share) — never a copy of a vanilla number.
- Hard: resources only with a cited deposit/production source; global totals within ±25 % of vanilla per resource.
- Preference: VP values follow the vanilla scale; ≤ 1 VP per 3 provinces on average outside major urban areas.
- Discretion: infrastructure model (document inputs: 1936 road/rail density proxies).

## 5. DECISION RULES
- If a city's coordinates fall on a sea/lake pixel after projection → use the nearest land province of the same state; log it.
- If two VP cities fall in one province → keep one VP (sum values, cap at the higher tier) and log.
- If owner is ambiguous (condominium, mandate, disputed) → pick the administering power at the start date; record alternatives in provenance `notes`; add the other claimant with `add_core_of` only if the design lists it.
- If population source is missing for a state → grid-share from the country total, `confidence=medium`; if the country total is also missing → `UNRESOLVED`, use grid only, `confidence=low`.
- If state_category thresholds give an obviously wrong result for a special case (e.g. wasteland with a naval base colony) → allowed override listed in the log with reason.

## 6. FAILURE MODES
1. Copying vanilla manpower/VPs/resources.
2. Assigning today's country (e.g. Pakistan in 1936, Israel in 1936).
3. VP in the wrong province due to projection/seam errors.
4. Localisation file without BOM or wrong header → all names show as keys.
5. Forgetting lakes: they may stay out of states (allowed), but never put sea provinces in.

## 7. EXECUTION WORKFLOW
1. INSPECT: G3 recorded; inputs present.
2. PLAN: country tag table and attribute CSVs with sources → log.
3. EXECUTE: generate files + localisation + merged provenance with final ids.
4. VERIFY (below).
5. REPORT: category distribution vs. vanilla, manpower totals by country vs. source totals (±2 %), VP distribution, resource totals, list of low-confidence states.

## 8. VERIFICATION COMMANDS
- `python3 .claude/skills/hoi4-map-modding/scripts/validate_map.py mod --json build/validate_p06.json` → 0 ERROR for all `STATE_*` codes except `STATE_CROSSES_REGION` (needs P07), and no new non-state errors.
- `python3 tools/check_provenance.py` → exit 0.
- `python3 -c "import codecs;b=open('mod/localisation/english/state_names_l_english.yml','rb').read(3);assert b==codecs.BOM_UTF8"`
- Grep check: every `STATE_<id>` and `VICTORY_POINTS_<prov>` key used exists in localisation.

## 9. STOP CONDITION & CHECKPOINT
Stop when verification passes. Commit `states(p06): start-date state files and localisation`. HARD STOP at Gate G4: audit A1 (different session) on all low-confidence states + 10 % random sample.
