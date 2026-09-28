# 2026-09-27 — first batch: decisions, in-game experiments, open checks

## Decisions (owner, 2026-09-27)
| ID | Decision | Consequence | Status |
|---|---|---|---|
| DEC-001 | Start date 1936-01-01 only; 1939 re-adjusted later | P04/P06 build 1936; 1939 lines only as border overlay | DONE |
| DEC-002 | Crop at 60° S like vanilla first (no Antarctica); revisit after testing | canvas 4608×2048 (60°S..90°N fits exactly) | OPEN → see CHK-001 |
| DEC-003 | Canvas width 4608 for stability | 56 km²/px; see CHK-002 for the 5120×2304 alternative | CHANGED (see 2026-09-28_rendering-countries-canvas.md#DEC-019) |
| DEC-004 | Central meridian 10.9° E | map edge in the Bering Strait | DONE |
| DEC-005 | High province density, accuracy of borders is the main goal; include 1914/1918 alt-history borders; more provinces in the Sahara | border-overlay rule in PROJECT_SPEC §3; budget ≈ 20k provisional | OPEN → EXP-03 |
| DEC-006 | More fine-grained states than vanilla; build from scratch; do **not** use Kovas' States Rework as a source | STATE_TARGET 1,800–2,500; hard constraint §6.7 | DONE |
| DEC-007 | Must work with vanilla focus trees (synergy); RT56 later | compat layer P13a/P13b, state ID anchoring | DONE |
| DEC-008 | Include historical releasable claimants | P06 countries + cores | DONE |
| DEC-009 | Tiny islands included, enlarged only very slightly; sea zones around them to make them identifiable | islands ≥ 8 px, minimal stamp; sea provinces ring key islands | DONE |
| DEC-010 | Dense rivers | P09 river threshold far below vanilla | DONE |
| DEC-011 | Game version 1.19.x (1.19.3 latest) | re-baseline in P00 | DONE (2026-09-27, CHK-003) |
| DEC-012 | Game at `E:\SteamLibrary\steamapps\common\Hearts of Iron IV` | `.claude/settings.local.json` | DONE (2026-09-27, P00-pre/P00: path verified, 1.19.3.0) |
| DEC-013 | Not public until complete | non-commercial licences acceptable for now; recorded per dataset | DONE |
| DEC-014 | Manpower from census data | P06 | DONE |
| DEC-015 | Real 1936 resource deposits | P06 | DONE |
| DEC-016 | Work moves to Claude Code CLI on the owner's PC with an agent fleet (overwatch, builders, reviewers, auditors, triage) | `docs/AGENT_SYSTEM.md` | DONE |
| DEC-017 | Owner can run in-game tests as often as needed | P12 in small batches | DONE |

## In-game experiments (agents build each test mod in P00b; owner loads it)
How every experiment works for you: the agent writes a tiny test mod into `build/experiments/EXP-xx/` and a `.mod` file into your `Documents/Paradox Interactive/Hearts of Iron IV/mod/` folder. You: open the launcher → enable only that test mod → start with the `-debug` launch option → do the listed steps → close → send `Documents/Paradox Interactive/Hearts of Iron IV/logs/error.log` (and a screenshot if asked).

| ID | Question it answers | What you do | Status |
|---|---|---|---|
| EXP-01 | Can two **sea** provinces be linked in `adjacencies.csv` without a land province in between? (needed to sail across the map edge away from the equator) | start as UK, pick a fleet in the test sea province, order it to the linked sea province; report whether it paths through the link and any error.log lines | OPEN |
| EXP-02 | How large may one province's footprint be before "TOO LARGE BOX"? | load 3 variants (a province spread 300 / 600 / 1,200 px); report which load cleanly | OPEN |
| EXP-03 | Real province-count ceiling | load dummy maps with 16k / 20k / 24k / 30k provinces; report which load and how long loading takes | OPEN |
| EXP-04 | Is the 8-pixel minimum still enforced in 1.19? | load a map with 6-, 7-, 8-pixel provinces; send error.log | OPEN |
| EXP-05 | Does `trees.bmp` need a particular size/aspect? | load 2 variants; screenshot the forests near a map edge | OPEN |
| EXP-06 | Off-globe filler as impassable lake provinces — any rendering or pathing issues? | pan to the curved map edges and the corners; try moving a fleet next to the edge | OPEN |
| EXP-07 | Do non-contiguous state IDs load? (matters if vanilla 1.19 has ID gaps) | load a map whose state IDs skip one number | OPEN |

## Checks to do later
| ID | Check | Who | Status |
|---|---|---|---|
| CHK-001 | After a first playable map: decide whether to add Antarctica back (full globe needs 4608×2304 or 5120×2560) | owner | OPEN |
| CHK-002 | With the 60° S crop, 5120×2304 (11.8 M px, ≈ vanilla's 11.5 M) gives 45 km²/px — 24 % finer than 4608×2048. Keep 4608 or switch? Decide after EXP-03 and a performance test | owner | DONE (2026-09-28, DEC-019: 5120×2304) |
| CHK-003 | Diff 1.19.x map/state formats against the 1.14.1 baseline (vanilla 1.19 has ≈ 1,081 states, ≈ 10,150 land provinces per MapChart — Tier 4) | agent (P00) | DONE (2026-09-27, `docs/logs/P00.md` §3): 1.19.3 has 1,081 states (IDs 1..1081, no gaps), 13,413 provinces (land 10,154 / sea 3,133 / lake 126), 304 regions; formats unchanged except buildings.txt type names + new types, airports.txt/rocketsites.txt removed, new state keys, `large_island` category, weatherpositions `small/big` |
| CHK-004 | Launcher mod format: does 1.19.x still use `descriptor.mod` + `.mod` with `replace_path`? | agent (P00, reads your install) | DONE (2026-09-27, P00 §3): Launcher v2 (`dlc_load.json` lists `mod/<file>.mod`); `.mod` keys = descriptor keys, absolute `path=`; `replace_path` in 18 of 53 Workshop descriptors (incl. `history/states`, `map/strategicregions`, `map/supplyareas`) |
| CHK-005 | Sizes of every `map/terrain/*.dds` in 1.19.x | agent (P00) | DONE (2026-09-27, P00 §4): 72 DDS; map-sized ones are colormap_rgb_cityemissivemask_a (2816×1024, 32-bit), colormap_water_0/1/2 (2816×1024 → 704×256, DXT5), fow_rgb_waterspec_a (2816×1024, DXT5); all others are size-independent tiling textures |
| CHK-006 | Map size and province count (limits only) of installed Kovas' States Rework (Workshop 2887517564) and Darkest Hour (1088848965) — **limits only**, nothing else is read | agent (P00) | DONE (2026-09-27, P00 §6): Kovas 5120×2560, 15,633 provinces, 1,295 state files; Darkest Hour installed as Workshop **3607150697** (1088848965 not installed): 5632×2304, 16,938 provinces, 1,815 state files; no installed mod exceeds 13.24 M px (see Q-007) |
| CHK-007 | Minimum province size — owner has no data; answered by EXP-04 | agent | OPEN |
| CHK-008 | trees.bmp size — answered by EXP-05 | agent | OPEN |
| CHK-009 | Merge branch `claude/laughing-newton-41591c` into `main` before the agent fleet starts (worktrees branch from `main`) | owner / me via PR | OPEN |
