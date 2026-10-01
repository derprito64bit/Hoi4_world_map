---
name: hoi4-map-modding
description: Hearts of Iron IV map modding reference and procedures — provinces.bmp/definition.csv, province generation, state creation/shaping/splitting/merging, strategic regions, adjacencies, supply/railways, raster layers (heightmap, terrain, rivers, normal, trees), positions (buildings/unitstacks), the Equal Earth projection canvas used by this repo, and an offline validator. Load before creating, editing, auditing or reviewing ANY file under map/, history/states/, common/state_category/, map/strategicregions/, or state/province localisation, or when writing prompts for agents that will.
---

# HOI4 Map Modding Skill

Operational knowledge for building a full-world Hearts of Iron IV map in the
**Equal Earth** projection. Everything here is either (a) measured from the
vanilla game files (1.19.3, re-measured at P00; 1.14.1 for older notes), (b) taken from the CWTools HOI4 schema, or
(c) community documentation marked with its evidence tier. See
`references/09-sources.md` before trusting any single claim.

## 1. Objective this skill serves

Produce map data the game loads with **zero MAP_ERROR lines** in `error.log`,
whose provinces and states are **geographically accurate** (traceable to a
cited boundary source) and whose gameplay density is deliberate, not accidental.

## 2. Progressive disclosure — read only what the task needs

| Task | Read |
|---|---|
| Any map work (always) | this file + `references/07-validation.md` |
| Editing/creating any map file | `references/01-file-formats.md` |
| Drawing or generating provinces | `references/02-provinces.md`, `references/06-equal-earth.md` |
| Creating / shaping / splitting / merging states | `references/03-states.md` |
| Strategic regions, weather, adjacencies, canals, supply, railways | `references/04-regions-adjacency-supply.md` |
| heightmap / terrain / rivers / trees / normal / colormap / cities | `references/05-rasters.md` |
| Numbers to calibrate against | `references/08-vanilla-baseline.md` |
| Packaging, descriptor, replace_path, localisation, vanilla script breakage | `references/10-mod-integration.md` |
| Camera, shaders, map edges, what the renderer can and cannot do | `references/11-rendering.md` |
| Evidence tiers, what is verified vs. unverified, open questions | `references/09-sources.md` |

Scripts (run from the repo root; need `numpy pillow`):
- `scripts/validate_map.py <mod_root> [--vanilla <game_root>] [--json out.json]` — offline invariant checker. Vanilla 1.19.3 baseline: **0 ERROR**, 5 WARN (6 with `STATE_CATEGORY_DUP` after the S10 fix) — see `references/08-vanilla-baseline.md`.
- `scripts/ee_project.py selftest|info|point|mask` — Equal Earth ↔ pixel canvas (verified against PROJ to 1e-6). Project defaults: 5120×2304, lon0 10.9, 60° S..90° N.

Target game version is **1.19.x**; the vanilla numbers in `references/08-vanilla-baseline.md` were re-measured on 1.19.3 at P00 (2026-09-27). Agents working in this repo are defined in `.claude/agents/` (see `docs/AGENT_SYSTEM.md`).

## 3. Hard invariants (never violate; the validator enforces most)

1. `provinces.bmp`: 24-bit BMP, uncompressed; width and height multiples of 256; W×H ≤ 13,238,272 (community ceiling).
2. `terrain.bmp`, `rivers.bmp`, `heightmap.bmp` exactly the same W×H as `provinces.bmp`; terrain/rivers 8-bit **indexed**, heightmap 8-bit greyscale. `world_normal.bmp` = W/2 × H/2, 24-bit (vanilla 1.19.3) or 32-bit (seen in a 1.19.3 mod). DIB header 40 bytes or 124-byte BITMAPV5 (vanilla 1.19.3 terrain.bmp and trees.bmp use V5; both load).
3. `definition.csv`: row 0 is `0;0;0;0;land;false;unknown;0`; IDs 1..N sequential, no gaps; every colour unique; every colour in the bitmap has a row and every row has ≥ 9 pixels (the engine logs every province ≤ 8 px, EXP-04 2026-09-30; project floor 9).
4. No X-crossings (4 provinces meeting at one pixel corner), including across the left/right wrap seam.
5. `coastal=true` **iff** a land province is 4-adjacent to a `sea` province (lakes don't count). Sea provinces: `true` iff touching land.
6. Land provinces: continent ≥ 1 (index into `continent.txt`, 1-based). Sea: continent 0.
7. Every land province is in **exactly one** state; no `sea` province is ever in a state; lakes may be in a state or not.
8. State IDs are exactly 1..S, no gaps — **a gap is fatal** (EXP-07, 2026-09-30: "Missing State ID", MAP_ERROR, crash on scenario start). File name `<id>-<Name>.txt` (a 1.19.3 mod uses `<id> - <Name>.txt`; both load).
9. A state never spans two strategic regions. Every province (land, sea, lake) is in exactly one strategic region.
10. Victory points, provincial buildings and naval bases reference provinces *inside that state*; naval bases only on coastal provinces.
11. `railways.txt`: consecutive provinces are adjacent (pixel-adjacent or via adjacencies.csv); all on land provinces that belong to states. `supply_nodes.txt` provinces are land provinces in states.
12. `adjacencies.csv` keeps its header row and the terminator line `-1;-1;;-1;-1;-1;-1;-1;-1`.
13. Never commit Paradox game files (vanilla bitmaps, vanilla text) to this repo. Reference them from a local install path.
14. **No province may cross the wrap seam** (pixels on both x=0 and x=W−1 forming one province): the engine measures its box as full map width → `TOO LARGE BOX` (EXP-08, 2026-09-30).
15. **Every naval (sea) strategic region is one pixel-connected piece** — counting its sea members only, 4-neighbour contact, the horizontal wrap counts, adjacency links do not. Otherwise fatal `MAP_ERROR: Naval strategic region … is fractioned!` (EXP-02b/08/09).
16. **No strategic region may hit the region-centre divide-by-zero.** The engine snaps each member's box to a 2-px grid (`x0 = 2*(xmin//2)`, `x0+w = 2*(xmax//2+1)`, y from the bottom), takes the integer mean of the box centres, and — if that point lies in no member box — divides by `mean.x − (rect_x0 + rect_w/2)` of the members' union rect. Zero → `INT_DIVIDE_BY_ZERO` crash at load (confirmed 6/6 in game, 2026-09-30). Gate: `regioncentre.guard_failures(..., observed={}) == 0` (`tools/experiments/regioncentre.py`); prefer means ≥ 1 px inside a member box.
17. Province bounding box: `TOO LARGE BOX` fires when **width > Tw ∈ [600, 1200) or height > Th ∈ [174, 300)** px (non-fatal; misplaces unit/ship stacks). Project limit 250 (land) / 180 (sea) max side stays inside both.

## 4. Decision rules (If → Then)

- Never use another mod (explicitly Kovas' States Rework) or vanilla HOI4 shapes as a source for geometry, names or attributes.

- If a source boundary and a gameplay wish conflict → keep the source boundary for states; express gameplay through province density, state category, VPs — never by moving a documented border.
- If two boundary sources disagree → record both in the state's provenance entry and choose the higher tier (09-sources.md); if same tier, mark `UNRESOLVED` and pick the one matching the start date.
- If a province would fall under 9 px, or its shape is a 1-px sliver → merge it into its neighbour inside the same state; never keep it for "accuracy".
- If a state would cross a strategic-region border → move the **region** border (regions are gameplay constructs), not the state.
- If an island is too small to hold 9 px at the canvas scale → either enlarge it to exactly the minimum viable footprint (document it) or drop it; never leave provinces of ≤ 8 px.
- If an in-game test is run → always launch with `-debug`: map-check lines (`TOO LARGE BOX`, `MAP_ERROR`, small-province lines) are written to error.log **only** in debug mode (2026-09-29); a clean log from a non-debug run proves nothing.
- If two seas must be joined across the wrap seam → make their pixels touch across x=0/x=W−1; never use an `adjacencies.csv` row (a `sea`-type row crashes the game, an empty-type row is measured the long way round — EXP-01).
- If a strategic region is built or changed → rerun the region-centre guard and the naval-contiguity check before anything else (invariants 15–16).
- If a coastline change touches any province → recompute coastal flags for the whole map; never hand-edit a single flag.
- If you renumber provinces → regenerate every file that stores province IDs (states, strategic regions, adjacencies, adjacency_rules, railways, supply_nodes, buildings.txt, unitstacks.txt, weatherpositions (region IDs), VP localisation) in the same commit. Prefer never renumbering.
- If the validator reports an ERROR after your edit → revert that edit before trying another approach.
- If you cannot test in-game (no game install in the container) → say so; the offline validator is necessary, not sufficient. Record what must be checked in-game.

## 5. Known failure modes

1. Editing provinces.bmp with a tool that anti-aliases, dithers or resamples (creates thousands of stray colours).
2. Saving BMPs as 32-bit, RLE-compressed, or with a colour profile; saving indexed images as RGB.
3. Hand-editing coastal flags or terrain in definition.csv instead of regenerating them.
4. Treating a modern admin boundary as the 1936 boundary without checking (e.g. post-war border changes).
5. Leaving vanilla scripts that reference vanilla state/province IDs (focuses, events, OOBs, capitals) → silent breakage or crashes.
6. Splitting a state and forgetting buildings.txt / VP localisation entries of the old ID (airports.txt / rocketsites.txt are legacy — absent in 1.19.3).
7. Provinces wider than ~600 px or taller than ~174 px, or any province crossing the seam → "TOO LARGE BOX" (confirmed 2026-09-30, see invariants 14 and 17).
8. Rivers thicker than 1 px, or rivers without exactly one source pixel.
9. Letting nudger-generated files in the user directory shadow the mod (see 07-validation.md).
10. Trusting a previous agent's summary instead of re-running the validator.
11. A strategic region whose box-centre mean lands exactly on its rect centre column → divide-by-zero crash at load (invariant 16). Regular/symmetric tilings (grid fillers, mirrored regions) are the high-risk case.
12. Donor-province remnants or region growth that leave a sea region in two pieces → fatal MAP_ERROR (invariant 15).
13. Adjacency rows across the wrap seam (EXP-01) and lake "filler" next to sea (EXP-06: the pathfinder routes through it, fleets get stuck).

## 6. Standard workflow for any map change

1. **Inspect**: `git status` clean; run validator on current state → save baseline JSON.
2. **Plan**: list every file the change touches (use the "renumbering" list above as the checklist). Write the plan into the task's log file before mutating.
3. **Mutate** with scripts, not by hand, whenever > 5 entities change. Scripts live in `tools/` and are committed.
4. **Verify**: validator ERROR count must be ≤ baseline and no new codes; diff the counts.
5. **Record**: provenance for any new/changed state (`data/provenance/states.csv`), commit atomically (`map(...)`, `states(...)`).
