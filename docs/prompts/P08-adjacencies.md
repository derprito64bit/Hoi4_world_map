# TASK P08: Adjacencies — straits, canals, impassable borders, seam links, rules

Run as `claude --agent overwatch`.

## 1. OBJECTIVE
`mod/map/adjacencies.csv` + `adjacency_rules.txt` giving every historically crossable strait, every canal open on 1936-01-01, impassable borders across real barriers, and Pacific seam links (method from EXP-01), with every row sourced and every rule localised.

## 2. WORK UNITS
| WU | Agent | Scope |
|---|---|---|
| P08a | researcher | `data/research/adjacencies/straits.csv`, `data/research/adjacencies/canals.csv`, `data/research/adjacencies/impassable.csv` (each row: endpoints lon/lat, type, source, opening date for canals) |
| P08b | pipeline-engineer (after P08a) | `tools/make_adjacencies.py`, `tests/test_adjacencies.py` (+ generated adjacency files and rule localisation) |
Review: fact-checker (P08a), code-reviewer + validator (P08b).

## 3. CONTEXT
Patterns: skill `references/04-regions-adjacency-supply.md` §2 and `references/01-file-formats.md` (strait = land–land through sea or lake; canal = sea–sea through land + rule; impassable; blank/comment lines allowed). Seam: `references/06-equal-earth.md` §4 and the EXP-01 result in `to-check/`.

## 4. CONSTRAINTS
- Hard: header first, terminator `-1;-1;;-1;-1;-1;-1;-1;-1` last; every rule named in the csv defined and localised.
- Hard: canals only if open on 1936-01-01 (Suez 1869, Kiel 1895, Panama 1914, Corinth 1893 — fact-checker confirms each, plus any others found).
- Hard (EXP-01 answered 2026-09-30): **no adjacency rows across the wrap seam** — a `sea`-type row with a sea Through crashes the game at start, an empty-type row is measured the long way round (1–2 years of travel). With the hybrid projection (DEC-035) seas meet natively by pixel contact at x=0/x=W−1, so no seam links are needed. Superseded text (kept for history): seam links generated in a separate commented block, using the method EXP-01 proved; if EXP-01 is still open → skip seam links and record that.
- Preference: straits only where the real crossing is ≤ ~40 km or historically used.

## 5. DECISION RULES
Endpoints already share a pixel edge → no row. Mountain wall without historical military crossing → `impassable` with the barrier cited (sparingly).

## 6. FAILURE MODES
Auto-generated straits everywhere coasts are close; canals opened after 1936; unlocalised rules.

## 7. VERIFICATION
- validator → 0 `ADJ_*` ERROR
- `python tools/make_adjacencies.py --check` (every row sourced; every rule localised; seam block matches EXP-01 method)

## 8. STOP
Merged → P09.
