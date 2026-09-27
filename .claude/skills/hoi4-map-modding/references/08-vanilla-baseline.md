# 08 — Vanilla baseline (measured, HOI4 1.14.1 "Bolivar", map files from a public text mirror)

> **Version warning:** the project targets **1.19.x**. MapChart (Tier 4) reports 1.17 at 1,046 states / 10,113 provinces and 1.19 at ≈ 1,081 states / ≈ 10,150 provinces (new states in SE Asia, China, the Pacific, Australia/NZ). Formats are expected to be unchanged, but every number below must be re-measured on the owner's 1.19 install in P00 (CHK-003) before being used as a calibration target.

Use these as calibration targets and sanity ranges, not as rules. Re-measure if the installed game version differs.

## Canvas
| File | Size | Format |
|---|---|---|
| provinces.bmp | 5632×2048 (22×256, 8×256), area 11,534,336 | 24-bit, 40-byte DIB, uncompressed |
| heightmap.bmp | 5632×2048 | 8-bit greyscale (L) |
| terrain.bmp | 5632×2048 | 8-bit indexed |
| rivers.bmp | 5632×2048 | 8-bit indexed |
| cities.bmp | 5632×2048 | 8-bit indexed |
| world_normal.bmp | 2816×1024 | 24-bit |
| trees.bmp | 1650×600 | 8-bit indexed |
| terrain/colormap_rgb_cityemissivemask_a.dds | 2816×1024 | DDS |

## Provinces
- 13,362 provinces (+ dummy 0): land 10,104, sea 3,133, lake 125. IDs sequential, colours unique, all bitmap colours defined.
- Land terrain: plains 3,025, forest 2,421, mountain 1,681, hills 1,344, desert 792, jungle 461, urban 243, marsh 137.
- Area (px): land p5 69 / p25 99 / median 161 / p75 422 / p95 1,253 / max 15,697 (min 22); sea p5 1,112 / median 2,330 / p95 3,645 / max 11,983 (min 102); lake median 115 (min 12).
- Bounding box max side: land median 19 / p95 54 / max 280; sea median 69 / p95 98 / max 179.
- Median land province area by map row band (256-row bands from the top): 276, 124, 112, 219, 216, 273, 566, 389 px — Europe/North America rows are densest.
- 488 provinces consist of more than one 4-connected pixel group. 0 X-crossings. 174 2×2 "checkerboard" diagonals (same province on a diagonal) — tolerated.
- No province touches both the left and right edges.
- Land pixels 4,052,732; sea pixels 7,431,344.
- Coastal: 2,330 land provinces flagged — exactly the set 4-adjacent to sea. 816 sea flagged vs 819 touching land (near-exact).
- Continents: europe 1 (3,287 land), north_america 2 (1,156), south_america 3 (556), australia 4 (376), africa 5 (730), asia 6 (3,520), middle_east 7 (479).

## States
- 969 states, ids 1..969 contiguous; every land province in exactly one state; 117 of 125 lakes inside states; 0 sea provinces in states.
- Provinces per state: min 1, p10 2, median 9, p90 21, max 70; 66 single-province states; 73 states not land-contiguous (islands) by pure pixel adjacency, 32 after adjacencies.csv links.
- Categories: rural 272, town 196, pastoral 144, city 113, wasteland 64, large_city 41, small_island 40, large_town 32, tiny_island 24, enclave 18, metropolis 17, megalopolis 8.
- Manpower: median 889,962, max 52,963,300.
- Infrastructure: 0 ×11, 1 ×221, 2 ×383, 3 ×273, 4 ×67, 5 ×1.
- Victory points (1,202 entries): 1 ×534, 2 ×79, 3 ×207, 5 ×181, 10 ×99, 15 ×33, 20 ×33, 25 ×7, 30 ×15, 40 ×5, 50 ×5 (+ singletons 4, 8, 12, 13). 9 VPs reference provinces outside their state (vanilla bugs).
- Resources (sum of single-line entries): steel 2,514 (144 states), aluminium 1,196 (83), chromium 1,369 (82), oil 1,236 (68), rubber 1,038 (31), tungsten 1,352 (66).
- 17 impassable states.

## Strategic regions
- 288 regions (ids 1..288). Kinds: 134 land-only, 54 land+lake, 57 sea-only, 41 sea+land (1–3 island provinces, one 34/34), 1 lake-only, 1 empty.
- Land region median 43 provinces (max 279); sea median 23 (max 92).
- 0 states span two regions. Every province in exactly one region.
- naval_terrain: water_deep_ocean 37, water_fjords 14, water_shallow_sea 12 (others default).
- Weather: 12 monthly periods per region.

## Adjacencies & supply
- adjacencies.csv: 140 land–land straits via a sea province; 3 sea–sea canals via a land province (Panama, Kiel, Suez, each with an adjacency rule); 70 impassable land–land.
- supply_nodes.txt: 713 hubs, all level 1, all on land, 683 on railway provinces.
- railways.txt: levels 1 ×448, 2 ×409, 3 ×28, 4 ×7; 3,512 consecutive pairs, all adjacent.

## buildings.txt line counts
supply_node 10,019; bunker 10,102; arms_factory 5,814; industrial_complex 5,814; anti_air_building 2,907; naval_base 2,330; coastal_bunker 2,330; floating_harbor 2,327; air_base / fuel_silo / nuclear_reactor / rocket_site / synthetic_refinery 969 each; radar_station 921; dockyard 500.

## Raster value facts
- heightmap: sea ≈ 89 (7.43 M of 7.43 M sea px), land 96–239 (mode 97–105), lakes 83–93.
- rivers.bmp: 254 (water bg) on 99.9 % of sea; 255 (land bg); river indices 3 (35k px), 11 (27k), 6 (13k), 4 (11k), 9, 7, 10; 316 sources, 250 flow-in, 14 flow-out pixels.
- terrain.bmp: index 15 on 96 % of sea pixels; land dominated by 0, 1, 4, 3, 7, 11, 22, 20.
