# Open questions (engine facts)

Seeded from skill `references/09-sources.md` §3 in P00 (2026-09-27). A question becomes a rule only after the listed test; record the result, date and evidence here and the owner-facing item in `to-check/`.
Evidence tiers: `references/09-sources.md` §1. P00 evidence: `docs/logs/P00.md`.

| ID | Question | Current handling | Test | Status |
|---|---|---|---|---|
| OPEN-1 | Can `adjacencies.csv` link two sea provinces **without** a land `Through` (wrap-seam Pacific links)? | plan: try `sea` type with sea Through, then empty type | EXP-01: move a fleet across the seam at 40° N; check naval pathing | OPEN — P00: vanilla 1.19.3 has 7 sea–sea rows with empty type and Through −1 (Gibraltar, Øresund, Bosphorus, Dardanelles, Hormuz, Otranto), but every pair already touches by pixels; they only attach a rule. Not evidence for non-touching links |
| OPEN-2 | Real province-count ceiling | provisional budget ≈ 20,000 | EXP-03 (16k/20k/24k/30k) | OPEN — P00: installed mods ship 20,005 / 20,309 / 21,670 provinces (load on 1.19.3 not verified); vanilla 13,413 |
| OPEN-3 | Off-globe fill as lake provinces — rendering/pathing side effects? | lakes in "off-globe" regions | EXP-06: load, pan the edges, AI naval pathing, error.log | OPEN |
| OPEN-4 | Exact "TOO LARGE BOX" threshold | land ≤ 250 px, sea ≤ 180 px bbox | EXP-02: binary search with a test province | OPEN — P00: vanilla 1.19.3 loads land 280 px (province 7855) and sea 179 px (8370) |
| OPEN-5 | Is W×H ≤ 13,238,272 a hard limit or memory-dependent? | stay ≤ 13,107,200 | EXP-08 (only if a larger canvas is proposed) | OPEN — P00: no installed mod exceeds 13,107,200 px (5120×2560 ×4, 5632×2304, 4096×3072) |
| OPEN-6 | Target is 1.19.x; baseline was measured on 1.14.1 | re-measure at P00 (CHK-003) | diff installed formats against 08-vanilla-baseline.md | **DONE (2026-09-27, P00)** — map/state formats unchanged except: buildings.txt type names/new types, airports.txt & rocketsites.txt gone, new state keys and `large_island` category, weatherpositions `small/big`; numbers re-measured (skill update S1–S11 proposed) |
| OPEN-7 | trees.bmp aspect — must it match the map aspect? | scale to 2:1 | EXP-05: visual check | OPEN — vanilla 1.19.3 still 1650×600 (2.75:1) on a 2.75:1 map |
| OPEN-8 | Are gaps in state IDs tolerated? | validator treats gaps as ERROR | EXP-07 | OPEN — P00: vanilla 1.19.3 IDs 1..1081 are contiguous, so anchoring needs no gaps (Q-005) |
| OPEN-9 | Is the 8-px province minimum enforced? | 8-px hard floor | EXP-04 | OPEN (Tier 1 hint) — `NGraphics.MINIMUM_PROVINCE_SIZE_IN_PIXELS = 8`, vanilla comment: "doesn't affect the game, just informs in the error.log" (Q-004) |
| OPEN-10 | Must `gfx/FX/constants.fxh` change for a non-vanilla canvas? | leave unchanged | EXP-08 visual check | OPEN (probably no) — P00: map size is engine-supplied (`MAP_SIZE_X/Y`, `FOW_POW2_X/Y` defined in no FX file); `MAP_NUM_TILES 4 × TEXELS_PER_TILE 512 = 2048` = terrain atlas side |
| OPEN-11 | What does `NGame.MAP_SCALE_PIXEL_TO_KM` (7.114 = 40,075 km / 5,632 px) drive, and what value fits the Equal Earth canvas? | vanilla value | read docs/defines usage; in-game compare displayed distances / air range | OPEN (Q-003) |
| OPEN-12 | Which `state_category` wins when a state declares it twice (4 vanilla states do)? | never emit duplicates | not needed if our generator never duplicates | OPEN (low priority) |


## Results after the in-game runs (2026-09-30; evidence `to-check/2026-09-28_exp-results.md`, `docs/logs/P00b.md`)
| ID | Answer | Evidence | Status |
|---|---|---|---|
| OPEN-1 | Links between non-touching seas work **within** the map (both row forms). **Across the wrap seam**: the `sea`-type row crashes the game at start (3/3); the empty-type row loads but is measured unwrapped (1–2 years of travel) → unusable. Superseded by DEC-035 (hybrid projection: native seam contact) | EXP-01 UK-A/B, SEAM-A/B | DONE |
| OPEN-2 | 16k, 20k, 24k(fix) and 30k load and play smoothly; the 24k crash was a region-centre divide-by-zero (the 2-px grid rule, confirmed 6/6), not a ceiling | EXP-03 + bisect probes | DONE |
| OPEN-3 | Lake filler next to sea traps fleets (routes go through it, fleets get stuck); looks like water. Superseded by DEC-035 (no off-globe area) | EXP-06, EXP-09a | DONE |
| OPEN-4 | `TOO LARGE BOX` (only logged with -debug; non-fatal; misplaces unit stacks) = width > Tw in [600, 1200) OR height > Th in [174, 300) px | EXP-02 -debug re-runs, EXP-02c | DONE (exact values unknown) |
| OPEN-5 | 14.4 M and 15.7 M px canvases crash at the same site after loading history; 5120×2304 (11.8 M) loads and plays | EXP-08, EXP-09 | DONE (ceiling consistent with ~13.2 M; not proven) |
| OPEN-7 | trees.bmp at 2:1 and 3:1 places forests where vanilla does | EXP-05 | DONE |
| OPEN-8 | State-ID gaps are fatal (crash on scenario start, "Missing State ID") | EXP-07 | DONE |
| OPEN-9 | Provinces ≤ 8 px are logged by `map.cpp:1842` ("should have at least 8"; 8 px itself is flagged), non-fatal | EXP-03-20k with -debug | DONE |
| OPEN-10 | No constants.fxh change needed; the 5120×2304 canvas renders (EXP-09) | EXP-09 | DONE |
| NEW-1 | Naval strategic regions must be pixel-contiguous (incl. across the wrap), else a fatal MAP_ERROR | EXP-02b-block-400, EXP-08-6144, EXP-09a | DONE |
| NEW-2 | A province crossing the wrap seam is measured as full width (TOO LARGE BOX) | EXP-08-5632 province 13511 | DONE |
| NEW-3 | Map-check lines (TOO LARGE BOX, MAP_ERROR, small provinces) are written to error.log only with `-debug` | block-400 runs with/without -debug | DONE |
| OPEN-11, OPEN-12 | unchanged (OPEN-11 decided by DEC-029: 6.74; OPEN-12 avoided by never emitting duplicates) | — | — |
