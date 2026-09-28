# 08 — Vanilla baseline (measured on HOI4 **1.19.3.0** "Operation Postern", owner's install, P00 2026-09-27)

Source: `docs/logs/P00.md` §2–§5 (numbers and key names only; no game file is in the repo). Use these as calibration targets and sanity ranges, not as rules. Re-measure if the installed game version changes. The older 1.14.1 numbers are kept in the footnote at the end for comparison.

## Canvas
| File | Size | Format |
|---|---|---|
| provinces.bmp | 5632×2048 (22×256, 8×256), area 11,534,336 | 24-bit, 40-byte DIB, uncompressed |
| heightmap.bmp | 5632×2048 | 8-bit greyscale, 40-byte DIB |
| terrain.bmp | 5632×2048 | 8-bit indexed, **124-byte DIB (BITMAPV5)** |
| rivers.bmp | 5632×2048 | 8-bit indexed, 40-byte DIB |
| cities.bmp | 5632×2048 | 8-bit indexed, 40-byte DIB |
| world_normal.bmp | 2816×1024 | 24-bit (32-bit also loads, SA-004) |
| trees.bmp | 1650×600 | 8-bit indexed, 124-byte DIB |
| terrain/Tree_season.bmp, Tree_tint.bmp | 8×16, 16×16 | 24-bit |

DDS tied to the map size (half resolution; for 5120×2304 → 2560×1152): `colormap_rgb_cityemissivemask_a.dds` 2816×1024 uncompressed 32-bit, 1 mip; `colormap_water_0/_1/_2.dds` 2816×1024 / 1408×512 / 704×256 DXT5, no mips (`_0/_1/_2` = graphics-quality levels); `fow_rgb_waterspec_a.dds` 2816×1024 DXT5, 12 mips. All other `map/terrain/*.dds` are size-independent tiling textures (atlas0 2048², borders, ice, mud, snow, rivers …) — reused from the game at build time, never committed.

## Provinces
- 13,413 provinces (+ dummy row 0 `0;0;0;0;land;false;unknown;0`): land 10,154, sea 3,133, lake 126. IDs 0..13413 contiguous, 8 columns on every row, colours unique, all bitmap colours defined.
- Land terrain: plains 3,031, forest 2,364, mountain 1,708, hills 1,352, desert 815, jungle 477, urban 265, marsh 142. Sea = ocean, lakes = lakes.
- Area (px): land p5 68 / p25 98 / median 160 / p75 422 / p95 1,248 / max 15,697 (**min 10**); sea p5 1,112 / median 2,330 / p95 3,645 / max 11,983 (min 102); lake median 118.5 (min 12). 0 provinces < 8 px.
- Bounding box max side: land median 19 / p95 54 / **max 280** (province 7855); sea median 69 / p95 98 / **max 179** (8370); lake max 159. → vanilla loads a 280-px land and a 179-px sea province.
- Median land province area by 256-row band (top → bottom): 278.5, 126, 114, 215, 230, 262, 570, 397 px.
- No province touches both the left and right edges.
- Pixels: land 4,052,725, sea 7,431,216, lake 50,395.
- Coastal: 2,362 land provinces flagged; sea true 816 / false 2,317; 3 lakes carry `coastal=true` (3217, 13098, 13180).
- Continents (land provinces): europe 1 (3,291), north_america 2 (1,154), south_america 3 (556), australia 4 (376), africa 5 (737), asia 6 (3,556), middle_east 7 (484). 77 of 126 lakes use continent 0.

## States (`history/states`, 1,081 files)
- **1,081 states, ids 1..1081 contiguous, no gaps.** File names: 967 `<id>-<Name>.txt`, 113 `<id> - <Name>.txt`, 1 `<id> -<Name>.txt` — all load.
- Every land province in exactly one state; 118 of 126 lakes inside states; 0 sea provinces in states.
- Provinces per state: min 1, p10 2, median 8, p90 19, max 70; 68 single-province states. 30 states non-contiguous after adjacencies.csv links.
- Categories: rural 321, town 224, pastoral 155, city 115, wasteland 66, small_island 46, large_city 40, large_town 40, tiny_island 25, enclave 19, metropolis 19, megalopolis 8, **large_island 3**. Four states declare `state_category` twice (190, 433, 440, 816) — which wins is unknown (validator WARN `STATE_CATEGORY_DUP`).
- Manpower: median 820,000, max 45,365,364.
- Infrastructure (1,050 states set it): 0 ×18, 1 ×293, 2 ×411, 3 ×263, 4 ×64, 5 ×1.
- Victory points (1,500 entries): 1 ×710, 2 ×146, 3 ×224, 5 ×196, 8 ×2, 10 ×113, 12 ×1, 13 ×1, 15 ×38, 20 ×35, 25 ×11, 30 ×14 (3 written `30.0`), 40 ×4, 50 ×5. 0 VPs outside their state.
- Resources (total, states): steel 2,591 (166), aluminium 1,201 (95), chromium 1,345 (93), oil 1,210 (84), rubber 1,032 (44), tungsten 1,346 (83), **coal 1,463 (153)**.
- 21 impassable states, each with `force_link_ownership_to`.
- Top-level keys: id, name, manpower, state_category, history, provinces, local_supplies (1,069), resources (512), buildings_max_level_factor (340), impassable (21), force_link_ownership_to (21), impassable_ignored_links (1).
- History keys: owner, add_core_of (1,531), victory_points, buildings, dated blocks (233), add_claim_by (41), controller (1), set_resistance / set_compliance / start_resistance, strategic_province_location (16), strategic_state_location (8), set_demilitarized_zone, set_variable, add_dynamic_modifier, `IF`/`if`, add_extra_state_shared_building_slots.
- Provincial building keys (inside `<province> = { }`): naval_base 534, bunker 42, coastal_bunker 59, naval_supply_hub 8, naval_headquarters 9, naval_facility 3, land_facility 2, dam 15, dam_mountain 1, 19 `landmark_*` keys.

## Strategic regions (304 files, ids 1..304 contiguous)
- Kinds: land 147, land+lake 55, sea 57, sea+land 41, lake 1, empty 3 (ids 15, 189, 253).
- Land median 42 provinces (max 279); sea median 25 (max 92).
- 0 states span two regions; every province in exactly one region.
- naval_terrain: water_deep_ocean 37, water_fjords 14, water_shallow_sea 12. 12 weather periods in all regions; `static_modifiers` in 10.
- `map/supplyareas/` still exists with 1 file.

## Adjacencies & supply
- adjacencies.csv (251 data rows, terminator on line 253 followed by 2 blank lines and a `#` comment line): 148 land–land straits via a sea province; 3 sea–sea canals via a land province (Panama, Kiel, Suez, each with a rule); 93 land–land impassable; **7 sea–sea rows with empty type, Through −1 and a rule** (Gibraltar N/S, Øresund, Bosphorus, Dardanelles, Hormuz, Otranto) between seas that already touch — the row only attaches the rule.
- supply_nodes.txt: 727 hubs, all level 1, all on land, 691 on railway provinces.
- railways.txt: 909 lines, levels 1 ×467, 2 ×406, 3 ×29, 4 ×7; 3,570 consecutive pairs, all adjacent; all rail provinces in states.

## buildings.txt (66,664 lines, 7 columns)
| Type | Lines | Per | Column 7 |
|---|---|---|---|
| arms_factory, industrial_complex | 6,486 each | 6 per state | 0 |
| anti_air_building | 3,243 | 3 per state | 0 |
| air_base, synthetic_refinery, radar_station, fuel_silo, stronghold_network, nuclear_reactor_spawn, rocket_site_spawn | 1,081 each | 1 per state | 0 |
| bunker, supply_node, special_project_facility_spawn | 10,154 each | 1 per land province | 0 |
| naval_base_spawn | 2,362 | 1 per coastal land province | **sea** province |
| coastal_bunker, naval_supply_hub, naval_headquarters | 2,362 each | 1 per coastal land province | 0 |
| floating_harbor | 2,334 | ~1 per coastal land province | **land** province |
| dockyard | 555 | 1 per coastal state | 0 |
| dam_spawn 58, landmark_spawn 23, locks_spawn 2 | — | specific states | 0 |

## Other map files
- `map/airports.txt` and `map/rocketsites.txt` **do not exist** in 1.19.3 (positions come from `buildings.txt`).
- `unitstacks.txt`: 265,355 lines, types 0..38; 7 land provinces without any entry still load; 124 of 126 lakes have none.
- `weatherpositions.txt`: 588 lines, sizes `small` 136 / `big` 452.
- `positions.txt` 0 bytes. `default.map` key set unchanged.
- `00_terrain.txt`: categories unknown, ocean, lakes, forest, hills, mountain, plains, urban, jungle, marsh, desert, water_fjords, water_shallow_sea, water_deep_ocean; palette table 25 entries (indices 0–22, 27, 31).

## Raster value facts
- heightmap: sea 89 on 99.98 % of sea pixels; land 86–239 (median 107).
- terrain.bmp: index 15 on 96.3 % of sea pixels.
- rivers.bmp: 254 water bg / 255 land bg; widths 3, 11, 6, 4, 9, 7, 10; 317 sources (0), 250 flow-in (1), 14 flow-out (2).

## Validator calibration (1.19.3)
`validate_map.py "$HOI4_GAME_DIR" --bbox-limit 250 --bbox-limit-sea 180` → 0 ERROR, 5 WARN: `DEF_SEA_CONTINENT` (sea 5257), `BBOX_LARGE` (land 7855, 280 px — only with `--bbox-limit 250`), `STATE_NONCONTIGUOUS` (30), `RIVERS_ON_SEA` (1,549 px), `RIVERS_THICK` (4). After the S10 fix a sixth code is expected: `STATE_CATEGORY_DUP` for states 190, 433, 440, 816 (CHK-014 confirms on the owner's PC).

---
**Footnote — 1.14.1 "Bolivar" (public mirror, for comparison only):** 969 states, 13,362 provinces (10,104 / 3,133 / 125), 288 regions; 140 straits, 70 impassable; categories without large_island; no coal; buildings used `naval_base`, `nuclear_reactor`, `rocket_site`; `airports.txt`/`rocketsites.txt` present; validator 9 ERROR `STATE_VP_OUTSIDE`, 4 WARN.
