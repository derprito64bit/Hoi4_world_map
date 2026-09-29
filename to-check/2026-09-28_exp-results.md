# 2026-09-28 — In-game experiment results (EXP-01..09)

Follows `2026-09-28_p00b-kit.md` (run order, what to send back). Owner reports; overwatch records them with the log evidence. Nothing here is claimed without the owner's report. The owner runs with 3 helper Workshop mods (Toolpack without the Errors, Modifier GUI Updated, Precise Buffs – Cheat Ideas) for cheats such as naval range; none contains `map/` or `common/defines/` files. From 2026-09-28 21:40 overwatch runs `install.py` at the owner's request; the owner ticks the mod in the launcher and plays.

## Results
| Build | Date | Owner report | Log evidence | Result |
|---|---|---|---|---|
| EXP-01-UK-A (non-touching seas 2942 → 8314, type `sea`, Through = sea 8314) | 2026-09-28 19:17 | "it went straight through" — the fleet's route ran straight across Britain via the link | `system.log`: Active Mod Count 1, P00b EXP-01-UK-A. `error.log`: no line from the mod (only the DLC checksum and 4 other Workshop mods' `supported_version`) | **Link works** (variant A, within the map) |
| EXP-01-UK-B (2942 → 8314, empty type, Through −1) | 2026-09-28 21:39 | "the fleet moves through britain not around it, cuts somewhere between Scotland and Wales". Owner read land provinces via `-debug`: Rosyth 6300 (state 121), Bristol 3369 (state 338); the linked seas are 2942/8314 | `system.log`: Active Mod P00b EXP-01-UK-B. `error.log`: no line from the mod | **Link works** (variant B, within the map) |
| EXP-01-SEAM-A (2560 Okhotsk → 3836 Bering, across the wrap seam; type `sea`, Through 3836) | 2026-09-28 21:46 and 21:48 | Mod reaches the main menu; **game crashes on clicking Start** after selecting a country (Soviet Union) | 2 crash dumps `crashes/hoi4_20260928_214628` and `…_214802`: both show only this mod active and the identical `EXCEPTION_ACCESS_VIOLATION` at `0x7FF61296748F`, in a TBB worker right after "Launching SINGLEPLAYER-game"; error.log empty. `naval_dist.cache` was rewritten at 21:46. UK-A, the same row form within the map, did not crash | **CRASH, reproducible (3 of 3)**. Try 3 (21:52, `crashes/hoi4_20260928_215259`) with fresh naval-distance caches crashed at the same address, so a stale cache is ruled out. The `sea`-type seam link crashes the game at start |
| EXP-01-SEAM-B (same pair, empty type, Through −1) | 2026-09-28 22:05 | **Game starts, no crash.** Fleet in 2560 (Penzhina Bay), right-click 3836: "it takes a path that goes through the entire soviet union, parts of europe and canada" = reading (b): link used, route drawn the long way across the whole map (not wrapped) | `system.log`: active SEAM-B + 3 helper Workshop mods (Toolpack without the Errors, Modifier GUI Updated, Precise Buffs – Cheat Ideas), none with `map/` or `common/defines/` files. No new crash dump after 21:52. error.log: no line from the mod | **Loads; link used but not wrapped (b).** Owner: the order shows "roughly a year or two" of travel; the fleet then ran out of fuel and returned to base. → the engine measures the link as the unwrapped distance (~5,350 px). **Useless for crossing the seam** |
| EXP-02-300 (land 1664 + sea 5426 spread to 300 px wide) | 2026-09-28 22:21 | "reached main menu, started and ran just fine, loaded very fast" | `system.log`: active EXP-02-300 + the 3 helper mods (no map files). `error.log`: no line with BOX/box/1664/5426 and no other line from the mod. game.log: 13,414 provinces, game launched. No new crash dump | **Loads** (300 px land and sea) |
| EXP-02-600 (land 1664 + sea 5367, 600 px wide) | 2026-09-28 | "got into menu, game runs, loaded very fast, a couple of seconds, no issues" | `system.log`: EXP-02-600 active; `error.log`: 0 lines with BOX/1664/5367; game launched; no new crash dump | **Loads** (600 px) |
| EXP-02-1200 (land 2972 + sea 8337, 1200 px wide) | 2026-09-28 22:28 | "same result as last time" (menu, game runs, loads in a couple of seconds) | `system.log`: EXP-02-1200 active; `error.log`: 0 lines with BOX/2972/8337; game launched; no new crash dump | **Loads** (1200 px) |
| EXP-02b (larger: full-width strip, solid blocks) | — | owner asked for larger tests; WU P00b-f2 | — | building |
| EXP-03-16k (16,000 provinces) | 2026-09-28 22:31 | "loaded, a couple of seconds into the scenario, runs very smooth as if it's still vanilla"; PC: 32 GB DDR4-3600, RX 6700 XT, Ryzen 5 5600X | game.log: **Loaded 16001 provinces**; defines → provinces 21 s (vanilla runs today: 20 s); game launched; error.log only the 5 usual non-mod lines; no new crash dump | **Loads, smooth** |
| EXP-03-20k (20,000 provinces + EXP-04: 19998 = 6 px, 19999 = 7 px, 20000 = 8 px) | 2026-09-28 22:34 | "same results as last time" (loads in seconds, smooth for 7 days) | game.log: **Loaded 20001 provinces**; defines → provinces 21 s; game launched; no crash dump. **EXP-04: no line in any log mentions 19998/19999/20000** (the define comment says sub-8-px provinces are logged; either the log line needs `-debug` or it isn't written in 1.19.3) | **Loads, smooth. 6/7-px provinces load silently** |
| EXP-03-24k (24,000 provinces) | 2026-09-29 07:41 | "crashes while trying to get to the game menu" | `crashes/hoi4_20260929_074145`: **EXCEPTION_INT_DIVIDE_BY_ZERO** at `0x7FF6129C4CDC` (main thread); game.log stops after "4470 defines loaded", before "Loaded N provinces" → crash during map/province loading. error.log: only graphics-init lines. Active: EXP-03-24k + the 3 helper mods | **CRASH on load.** Ceiling or build defect still undetermined → next: 30k as the discriminator, then bisect (21k/22k) if needed |
| EXP-03-30k … EXP-07 | — | — | — | pending |

## EXP-01 conclusion (2026-09-28)
- Within the map, a link row joins two non-touching seas (both forms work, no error.log line).
- Across the wrap seam: the `sea`-type row with a sea Through **crashes the game at start** (3/3, even with fresh caches). The empty-type row loads, but travel is measured the long way across the map (one to two years) → **seam links are not a usable method.**
- Consequence: DEC needed on the seam-crossing method (Q-009 below).

## Interim reading (before SEAM runs)
- Both row forms join two non-touching sea provinces with no error.log line: A (`sea` type, sea Through) and B (empty type, Through −1). B is the simpler form (no dummy Through) and is the candidate for seam links. SEAM-A/B show whether a link survives the wrap seam, which is what the seam-link method needs.

## EXP-02 reading
- A 1-px strip province with a bounding box 300 / 600 / 1200 px wide loads for both land and sea, with no BOX line in error.log. The spec limit BBOX_MAX 250/180 is far below what loads. Caveat: the strips have few pixels. EXP-02b (full-width strip; solid 400×400 and 800×800 blocks) tests large *filled* provinces before any BBOX_MAX change (owner gate).
- Q-009 note: option A (sea corridors whose pixels touch across the wrap) uses the same mechanism as vanilla's own Pacific wrap, where seas touch at x=0/x=5631 and fleets cross normally, so it needs no separate engine test. Only its look (EXP-09/P14) remains open.

## Questions for the owner
| ID | Question | Options | Status |
|---|---|---|---|
| Q-009 | How do ships cross the map's left/right edge where the Equal Earth outline curves away (Bering Sea, the Arctic)? `adjacencies.csv` links can't do it (EXP-01). | **A (recommended):** real sea corridors — draw a band of sea provinces through the off-globe filler so the water pixels touch across the wrap edge. The engine then measures the distance the short way, as vanilla's own Pacific wrap does. The corridor is visible in the off-globe area; P14/EXP-09 shading can soften it. Uses the same mechanism as vanilla's own Pacific wrap (no separate engine test needed). **B:** no crossing at high latitudes: ships go around via the equator, where the two edges meet naturally (Bering and Arctic routes become very long). **C:** move the seam (the central meridian lon0 10.9) so it crosses as little high-latitude sea as possible; the Arctic is cut anyway, so C reduces the problem but does not remove it. | OPEN |

## Open owner items
| ID | Item | Status |
|---|---|---|
| CHK-015 | remaining EXP runs | OPEN |
| CHK-017 | does `-debug` show province IDs on hover? | DONE (2026-09-28): yes, the owner read province and state IDs with `-debug` |
