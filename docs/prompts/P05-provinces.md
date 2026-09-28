# TASK P05: Provinces — provinces.bmp, definition.csv, continent.txt (skeleton + split-on-refine)

Run as `claude --agent overwatch`. Agent gate **G3** after the skeleton pass.

## 1. OBJECTIVE
Generate every province — land (inside states), sea, lake, off-globe filler — with 0 validator errors on bitmap/definition checks, within the confirmed `PROVINCE_BUDGET`, with borders that follow every state border **and** every line of the 1914 / 1918–1923 / 1939 overlay; later refinement waves split provinces without renumbering existing IDs.

## 2. WORK UNITS
| WU | Agent | Scope |
|---|---|---|
| P05a | pipeline-engineer | `tools/provinces/**`, `tools/make_provinces.py`, `tests/test_provinces.py` (writes `mod/map/provinces.bmp`, `mod/map/definition.csv`, `mod/map/continent.txt`, `build/pid.npy`, `build/state_raster.npy`, `data/provenance/province_ids.csv` via the generator) |
| P05b (after each P04-W wave) | pipeline-engineer | same scope — **split mode**: new state/overlay lines split existing provinces; the larger part keeps its ID, others get appended IDs |
Review: code-reviewer, visual-qa (provinces + seam + off-globe previews), validator.

## 3. CONTEXT
- Algorithm and rules: skill `references/02-provinces.md` §2, §4 (density + border rule), §5, §6; `references/06-equal-earth.md` §3–4 (off-globe filler = lake provinces in dedicated regions unless EXP-06 says otherwise; seam).
- Budget and limits: PROJECT_SPEC §2 (`PROVINCE_BUDGET` as confirmed by EXP-03; `BBOX_MAX` from EXP-02; 8-px floor from EXP-04, run inside the EXP-03 kit).
- Inputs: `build/masks/surface.npy`, state polygons (skeleton or wave), overlay lines, VP/port/capital seeds from state attributes.

## 4. CONSTRAINTS
- Hard: no province crosses a state border, an overlay line, the seam, or a surface-class border.
- Hard: SKILL.md invariants 1–6; ≥ 8 px (target ≥ 30 px land); 0 X-crossings (incl. seam); bbox ≤ limits.
- Hard: deterministic (seeded; two runs → identical SHA-256); colours unique, never `0,0,0`.
- Hard: ID policy — skeleton pass assigns IDs (land by state → sea → lake → off-globe); after the first merge IDs are **never renumbered or reused**; splits append.
- Hard: `continent.txt` = the 7 vanilla continents (Antarctica cropped, DEC-002).

## 5. DECISION RULES
- Print the budget table first (density count + overlay splits + sea + lakes + off-globe); over budget → raise `A_base` globally, never drop overlay lines.
- State rasterises to < 8 px → merge into a neighbour in the same parent unit (log) or, if historically significant, enlarge minimally (DEC-009).
- X-crossing fixer loops > 20× at one spot → reassign the 2×2 block to the majority province in its 5×5 neighbourhood (log).
- Sea province over the bbox limit → split it; ring significant islands with their own sea provinces (DEC-009).

## 6. FAILURE MODES
Provinces generated before states/overlay were rasterised; non-deterministic IDs; slivers from the X-fixer; 8-connected coastal logic; renumbering on refine.

## 7. VERIFICATION
- `python .claude/skills/hoi4-map-modding/scripts/validate_map.py mod --vanilla "$HOI4_GAME_DIR" --bbox-limit 250 --bbox-limit-sea 180 --json build/validate_p05.json` → 0 ERROR among bitmap/definition/X/coastal codes (state/region codes pending P06/P07 are listed as expected)
- `python tools/make_provinces.py --check` (no province spans two states / overlay sides / surface classes / the seam; count ≤ budget; no ID changed vs. previous `province_ids.csv` except appended)
- run twice → identical `python -c "import hashlib,sys;[print(hashlib.sha256(open(f,'rb').read()).hexdigest(),f) for f in sys.argv[1:]]" mod/map/provinces.bmp mod/map/definition.csv`

## 8. STOP
Skeleton: G3 recorded by overwatch → P13a + P06. Split mode: merge after each wave, then rebuild downstream.
