# TASK P04: State geometry — skeleton pass, then refinement waves

Run as `claude --agent overwatch`. Two modes (PROJECT_SPEC §12). Agent gate **G2** (history-auditor PASS) after each refinement wave.

## 1. OBJECTIVE
- **P04-S (skeleton):** one polygon per 1936 sovereign state, colony, protectorate, mandate and princely-state agency, covering all land, so the whole pipeline can run end-to-end early.
- **P04-W (waves):** replace skeleton polygons country by country with accurate 1936 states (fine-grained, target 1,800–2,500 worldwide) plus the 1914 / 1918–1923 / 1939 border overlay lines, each state traceable to Tier 1–2 evidence.

## 2. WORK UNITS
| WU | Agent | Scope |
|---|---|---|
| P04-S | pipeline-engineer | `tools/states_skeleton.py`, `tests/test_states_skeleton.py` (writes `build/states/skeleton.geojson`) |
| P04-S-list | state-builder | `data/countries/tags.csv`, `data/countries/status_calibration.csv`, `data/provenance/countries.csv` — 1936 starting tags per PROJECT_SPEC `COUNTRIES` and releasables |
| P04-W-<ISO3> (one per country; big ones split: USSR by republic/oblast groups, China by province groups, British India by province + agency, USA by census region, French West Africa by colony…) | state-builder | `data/states/<continent>/<ISO3>*`, `data/provenance/states_<ISO3>.csv`, `data/research/<ISO3>/**` |
Wave order: Europe → Middle East & North Africa → East Asia → South & Southeast Asia → Americas → sub-Saharan Africa → Oceania. ≤ 6 WUs at a time, disjoint scopes (`wu_check.py overlap` = 0).
Review per WU: fact-checker (all rows) → history-auditor (sample; full audit at the wave's G2) → visual-qa (overlay previews) → triage.

## 3. CONTEXT
- Method (mandatory): skill `references/03-states.md` §2–3 incl. §3.2b overlay; `.claude/agents/state-builder.md`.
- Country status rules + calibration: PROJECT_SPEC `COUNTRIES`, `data/countries/status_calibration.csv` (fact-checker resolves every `VERIFY` row first — e.g. FC-001 Belgian Congo).
- Source leads: `data/research/catalogue/<region>.md` (P02b, fact-checked).
- Density for province estimates: PROJECT_SPEC §3 (45.4 km²/px).

## 4. CONSTRAINTS
- Hard: polygons never cross a 1936 sovereign border; colonies/protectorates follow their 1936 administrative units; princely states grouped into their agencies unless large enough for their own state(s).
- Hard: every state has a provenance row, Tier 1–2 (Tier 3 only with `confidence=low` + an A2 research task).
- Hard: **never** use other mods (explicitly Kovas' States Rework) or vanilla HOI4 shapes/names/attributes; vanilla is used only by P13a as a "missing territory" coverage check (DEC-025).
- Hard: polygons tile the land mask (gaps/overlaps ≤ 0.5 % per state, reported).
- Preference: 2–25 provinces per state at target density; start-date names.

## 5. DECISION RULES
- Modern boundary used → cite why it equals 1936 (source saying no change, or IoU ≥ 0.95 against a Tier 1 1936 map) — else Tier 3.
- Sources disagree → both in notes; higher tier wins; tie → closest date; still tied → UNRESOLVED + A2 research WU.
- Country status unclear → the entity stays inside its administering power (releasable) until the fact-checker resolves it.
- > 10 % of a WU's states UNRESOLVED → stop that WU, report.

## 6. FAILURE MODES
Modern borders used for 1936 (post-1945 Poland/USSR, post-colonial Africa, merged princely states); status accepted because someone asserted it; states > 25 provinces; citations to homepages; "not found" treated as "didn't exist".

## 7. VERIFICATION
- P04-S: `python tools/states_skeleton.py --check` (tiles the mask; one feature per starting tag/dependency; every tag in `data/countries/tags.csv`)
- P04-W: `python tools/check_provenance.py --geometry data/states/<continent>/<ISO3>.geojson`; tiling/sovereign-border checks via the WU's acceptance script; fact-checker 0 WRONG; visual-qa overlay previews 0 P0.

## 8. STOP
P04-S merged → go straight to P05 skeleton. Each P04-W wave: G2 audit PASS → rebuild downstream (`python tools/build_all.py --from provinces`) → P12 smoke round for the owner.
