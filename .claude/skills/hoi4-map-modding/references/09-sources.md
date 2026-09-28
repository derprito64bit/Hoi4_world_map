# 09 — Sources, evidence tiers, open questions

## 1. Evidence tiers for engine facts
| Tier | Source | Used for |
|---|---|---|
| 1 | Installed game files of the target version (`map/`, `common/`, `history/`, `documentation/*.md`); in-game `error.log` behaviour | formats, palettes, invariants, what loads |
| 2 | A mod built for 1.19.3 (Kaiserreich, public GitHub) — used **only** to confirm file formats/syntax under 1.19 (checked 2026-09-28), never for geometry, names or attributes | formats |
| 1* | Public mirror of vanilla text/map files: `github.com/cbrzeczysz/hoi4-history` (commit "1.14.1 - Bolivar", 2024-03-07) — measured for 08-vanilla-baseline.md | same as Tier 1 **for 1.14.1**; re-verify on newer versions |
| 2 | CWTools HOI4 rules `github.com/cwtools/cwtools-hoi4-config` (`Config/history/states.cwt`, `Config/map/regions.cwt`, `Config/map/map_consolidated.cwt`) | field names, cardinalities, value ranges |
| 3 | Paradox wiki (Map modding, State modding, Nudger, Strategic region modding, Supply areas) — only via search snippets in this environment | limits and error texts marked [C] |
| 4 | Forums, Steam guides, YouTube, MapChart, tool READMEs (HOI4 Province Editor, MapGen, hoi4-mod-maker) | leads only |
| — | **Other mods** (Kovas' States Rework, Darkest Hour, …) | never a source for geometry, names or attributes; installed map mods may be measured for engine limits only (map size, province count) |
Rule: Tier 3–4 claims stay marked [C] until an in-game test (Tier 1) confirms them; record confirmations in `docs/OPEN_QUESTIONS.md`.

## 2. Geographic data sources (for agents building the map — verify licence and reachability before use)
| Need | Candidate sources (Tier for boundaries per 03-states §3.1) |
|---|---|
| Coastline, land, lakes, rivers, admin-1 (modern) | Natural Earth 10 m/50 m (public domain; GeoJSON mirror `github.com/nvkelso/natural-earth-vector`, reachable from the container via raw.githubusercontent.com) |
| Modern admin-1/2 detail | GADM, geoBoundaries (Tier 2, only where unchanged since start date) |
| Sovereign borders at the start date | CShapes 2.0 (ETH Zürich, 1886–2019) — Tier 1 for country borders |
| Historical admin units | national historical GIS (e.g. MPIDR Population History GIS Collection for Europe; Newberry Atlas of Historical County Boundaries for the US; China Historical GIS; others per country) — Tier 1 |
| Elevation / bathymetry | ETOPO 2022 or GEBCO grid |
| Land cover | ESA WorldCover / MODIS MCD12Q1 / Copernicus Global Land Cover |
| Rivers | HydroRIVERS (HydroSHEDS) or Natural Earth rivers |
| Population 1936 | HYDE 3.x gridded population back-casts + national censuses nearest 1936 |
| Railways 1936 | historical railway atlases / national railway GIS; Tier 3 unless a GIS exists |
| Climate normals for weather | CRU TS monthly climatology, WorldClim (modern; flag as proxy) |

Network note: the owner's PC has full network access; only the cloud sessions that wrote this skill were restricted (Paradox wiki blocked there).

## 3. Open questions (UNRESOLVED — each needs the listed test before it becomes a rule)
The owner-facing versions of these tests are EXP-01..07 in `to-check/2026-09-27_decisions-and-checks.md` (OPEN-1 = EXP-01, OPEN-2 = EXP-03, OPEN-3 = EXP-06, OPEN-4 = EXP-02, OPEN-7 = EXP-05).
| ID | Question | Current handling | Test |
|---|---|---|---|
| OPEN-1 | Can adjacencies.csv link two sea provinces **without** a land `Through` (wrap-seam Pacific links)? | plan: try `sea` type with sea Through, then empty type | in-game: move a fleet across the seam at 40°N; check naval supply pathing |
| OPEN-2 | Real province-count ceiling | provisional budget ≈ 20,000 | EXP-03 (16k/20k/24k/30k) |
| OPEN-3 | Off-globe fill as lake provinces — any rendering/pathing side effects? | lakes in "off-globe" regions | load, pan the map edges, check AI naval pathing and error.log |
| OPEN-4 | Exact "TOO LARGE BOX" threshold | land ≤ 250 px, sea ≤ 180 px bbox | binary search with a test province |
| OPEN-5 | Is W×H ≤ 13,238,272 a hard limit or memory-dependent? | stay ≤ 13,107,200 | only relevant if a larger canvas is proposed |
| OPEN-6 | ~~Target is 1.19.x (owner); baseline measured on 1.14.1~~ **closed 2026-09-27**: re-measured on 1.19.3 at P00, see 08-vanilla-baseline.md | re-measure at P00 (CHK-003) — done | diff installed map/common/history formats against 08-vanilla-baseline.md |
| OPEN-8 | Are gaps in state IDs tolerated? (vanilla-ID anchoring may need it) | validator treats gaps as ERROR | EXP-07 |
| OPEN-7 | trees.bmp aspect — must it match the map aspect? | scale to 2:1 | visual check |

## 4. Measurement provenance
All numbers in 08-vanilla-baseline.md were produced by scripts in the session that wrote this skill (pixel scans of provinces.bmp joined to definition.csv, parsing of history/states and map/strategicregions). `validate_map.py` reproduces the invariant counts; re-run it against an installed game with `validate_map.py <game_root>`.
