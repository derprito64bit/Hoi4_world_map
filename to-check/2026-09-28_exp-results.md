# 2026-09-28 — In-game experiment results (EXP-01..09)

Follows `2026-09-28_p00b-kit.md` (run order, what to send back). Owner reports; overwatch records them with the log evidence. Nothing here is claimed without the owner's report.

## Results
| Build | Date | Owner report | Log evidence | Result |
|---|---|---|---|---|
| EXP-01-UK-A (non-touching seas 2942 → 8314, type `sea`, Through = sea 8314) | 2026-09-28 19:17 | "it went straight through" — the fleet's route ran straight across Britain via the link | `system.log`: Active Mod Count 1, P00b EXP-01-UK-A. `error.log`: no line from the mod (only the DLC checksum and 4 other Workshop mods' `supported_version`) | **Link works** (variant A, within the map) |
| EXP-01-UK-B | — | — | — | pending |
| EXP-01-SEAM-A / SEAM-B | — | — | — | pending |
| EXP-02 … EXP-07 | — | — | — | pending |

## Interim reading
- A `sea`-type row with a sea province as Through joins two sea provinces that don't touch, with no error.log line. UK-B shows whether the empty-type row does the same. SEAM-A/B show whether a link survives the wrap seam, which is what the seam-link method needs.

## Open owner items
| ID | Item | Status |
|---|---|---|
| CHK-015 | remaining EXP runs | OPEN |
| CHK-017 | does `-debug` show province IDs on hover? | OPEN (not reported yet) |
