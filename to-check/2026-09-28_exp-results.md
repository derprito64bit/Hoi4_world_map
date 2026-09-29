# 2026-09-28 — In-game experiment results (EXP-01..09)

Follows `2026-09-28_p00b-kit.md` (run order, what to send back). Owner reports; overwatch records them with the log evidence. Nothing here is claimed without the owner's report. From 2026-09-28 21:40 overwatch runs `install.py` at the owner's request; the owner ticks the mod in the launcher and plays.

## Results
| Build | Date | Owner report | Log evidence | Result |
|---|---|---|---|---|
| EXP-01-UK-A (non-touching seas 2942 → 8314, type `sea`, Through = sea 8314) | 2026-09-28 19:17 | "it went straight through" — the fleet's route ran straight across Britain via the link | `system.log`: Active Mod Count 1, P00b EXP-01-UK-A. `error.log`: no line from the mod (only the DLC checksum and 4 other Workshop mods' `supported_version`) | **Link works** (variant A, within the map) |
| EXP-01-UK-B (2942 → 8314, empty type, Through −1) | 2026-09-28 21:39 | "the fleet moves through britain not around it, cuts somewhere between Scotland and Wales". Owner read land provinces via `-debug`: Rosyth 6300 (state 121), Bristol 3369 (state 338); the linked seas are 2942/8314 | `system.log`: Active Mod P00b EXP-01-UK-B. `error.log`: no line from the mod | **Link works** (variant B, within the map) |
| EXP-01-SEAM-A (2560 Okhotsk → 3836 Bering, across the wrap seam; type `sea`, Through 3836) | 2026-09-28 21:46 and 21:48 | Mod reaches the main menu; **game crashes on clicking Start** after selecting a country (Soviet Union) | 2 crash dumps `crashes/hoi4_20260928_214628` and `…_214802`: both show only this mod active and the identical `EXCEPTION_ACCESS_VIOLATION` at `0x7FF61296748F`, in a TBB worker right after "Launching SINGLEPLAYER-game"; error.log empty. `naval_dist.cache` was rewritten at 21:46. UK-A, the same row form within the map, did not crash | **CRASH** (1st/2nd try). Retry 3 with the naval-distance caches moved aside (backup `build/cache_backup/2026-09-28_2148/`) pending; then SEAM-B |
| EXP-02 … EXP-07 | — | — | — | pending |

## Interim reading
- Both row forms join two non-touching sea provinces with no error.log line: A (`sea` type, sea Through) and B (empty type, Through −1). B is the simpler form (no dummy Through) and is the candidate for seam links. SEAM-A/B show whether a link survives the wrap seam, which is what the seam-link method needs.

## Open owner items
| ID | Item | Status |
|---|---|---|
| CHK-015 | remaining EXP runs | OPEN |
| CHK-017 | does `-debug` show province IDs on hover? | DONE (2026-09-28): yes, the owner read province and state IDs with `-debug` |
