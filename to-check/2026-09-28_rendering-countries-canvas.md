# 2026-09-28 — countries, canvas, rendering, fact-checking

References earlier items from `2026-09-27_decisions-and-checks.md`.

## Decisions (owner, 2026-09-28)
| ID | Decision | Consequence | Status |
|---|---|---|---|
| DEC-018 | Starting countries = only entities that were independent **on paper** in 1936 and ruled their own territory (examples given: Egypt, Indochina). Colonies and princely states are not separate starting countries. | PROJECT_SPEC `COUNTRIES`; map states still follow colonial/provincial administrative units for accuracy; colonies/princely states can be releasables (DEC-008). Fact-checker verifies each tag's 1936 status. | DONE (confirmed 2026-09-28) |
| DEC-019 | Canvas **5120 × 2304** (owner had misread 4608 as vanilla) | 45.4 km²/px; 60° S crop leaves 14 spare rows top and bottom. Supersedes DEC-003 and CHK-002. | DONE |
| DEC-020 | Bigger canvas allowed if the new map needs it | only if EXP-08 proves the engine loads it; P00 measures the sizes of installed large-map mods | OPEN → EXP-08 |
| DEC-021 | Off-globe area must look as seamless as vanilla while moving/zooming | P14 rendering phase: camera defines + colour-only shader treatment (no geometry warp — engine limitation, see `references/11-rendering.md`) | OPEN → EXP-06, EXP-09 |
| DEC-022 | Agents place all building/unit positions (no manual nudger work) | P10 fully scripted | DONE |
| DEC-023 | Experiments EXP-01/02 approved, with their limitations documented | P00b includes a "what this test cannot prove" line per experiment | DONE |
| DEC-024 | Dedicated fact-checking agent | new agent `fact-checker` (100 % of claim rows) + `visual-qa` + `gfx-engineer` | DONE |
| DEC-025 | Vanilla may be used only as a coverage check for forgotten territories, never for shapes | P13a coverage report doubles as the "did we miss a territory" check | DONE |
| DEC-026 | Full network access on the owner's PC | no download workarounds needed in P02 | DONE |
| DEC-027 | Audits by agents; add as many systems as needed | fleet now 12 agents (`docs/AGENT_SYSTEM.md`) | DONE |
| DEC-028 | Owner asked how best to build efficiently | walking skeleton first (PROJECT_SPEC §12) | DONE (approved 2026-09-28) |

## Engine limitation found (research 2026-09-28)
HOI4 has **no map projection, globe or zoom-dependent warp**. The map is a flat heightmapped plane; units, icons and clicks are tied to the pixel grid, so geometry can't be distorted per zoom level. We bake Equal Earth into the bitmaps; zoom-dependent effects are limited to colour/opacity (vanilla already fades borders by zoom). Shaders in `gfx/FX` and camera defines are moddable (Tier 3 evidence; exact behaviour tested in EXP-09).

## New experiments
| ID | Question | Owner steps | What it cannot prove | Status |
|---|---|---|---|---|
| EXP-08 | Does the engine load canvases beyond the ~13.24 M px community ceiling (e.g. 5632×2560, 6144×2560)? Do `gfx/FX/constants.fxh` map constants need changing for a new canvas? | load each variant, pan to all four edges, report load time + error.log | long-game stability and performance with a full province set (EXP-03 + later P12) | OPEN |
| EXP-09 | Edge treatment prototype: off-globe filler + tuned `CAMERA_OUTSIDE_MAP_DISTANCE_*` / `CAMERA_MAX_HEIGHT` + a minimal shader fade | screenshots at 5 zoom levels at the curved edges and the Pacific seam | the final look (needs the real rasters from P09) | OPEN |

## Limitations of the earlier experiments (added 2026-09-28)
| ID | Cannot prove |
|---|---|
| EXP-01 | AI naval planning and supply across the seam at full scale — only that a fleet can path over one link |
| EXP-02 | the exact threshold (only the three sizes tested); behaviour for sea vs land provinces may differ — test both if the first run is ambiguous |
| EXP-03 | late-game performance; the ceiling may depend on RAM/VRAM of the owner's PC |
| EXP-04 | whether a province that loads is still clickable/usable at 8 px |
| EXP-05 | visual quality with the final terrain |
| EXP-06 | AI behaviour near the filler over a whole game |
| EXP-07 | behaviour of vanilla scripts that iterate over state IDs |

## Questions for the owner
| ID | Question | Status |
|---|---|---|
| Q-001 | ~~Confirm the reading of DEC-018: starting tags = sovereign states + entities independent on paper with their own government (e.g. Egypt, Iraq, Manchukuo, Tannu Tuva, Nepal; Indochina's protectorates Annam/Cambodia/Laos/Tonkin as you described) — **not** colonies (e.g. Senegal, Belgian Congo) and **not** princely states (e.g. Hyderabad), which start inside their colonial owner as states and exist as releasables. Correct?~~ | DONE (2026-09-28): owner confirmed; asked for rigorous fact-checking → FC-001 |
| Q-002 | Approve the walking-skeleton build order (PROJECT_SPEC §12)? | DONE (2026-09-28): approved — rough whole-world build first, then refinement waves |

## Fact-check items
| ID | Item | Status |
|---|---|---|
| FC-001 | **Belgian Congo in 1936.** Owner: "independent on paper". Claude: the *Congo Free State* (1885–1908) was nominally independent (personal possession of Leopold II); Belgium annexed it — Colonial Charter approved 18 Oct 1908, sovereignty transferred 15 Nov 1908 — so in 1936 it was a Belgian colony. Sources so far are Tier 3 (EBSCO Research Starters, Britannica); the fact-checker must confirm with the Tier 1 annexation law/charter text. Until resolved: treat as colony (map states of BEL, releasable). Added as CAL-001 in `data/countries/status_calibration.csv` together with 8 other tricky cases. | OPEN (fact-checker) |
