# 01 — Map file formats (exact)

Evidence: **[V]** = observed in vanilla 1.14.1 files; **[S]** = CWTools schema;
**[C]** = community docs (Paradox wiki via search snippets) — verify in game.
Paths are relative to the mod root.

Format evidence: 1.14.1 vanilla files [V] and a mod built for **1.19.3** (checked 2026-09-28: all map files parse with 0 validator errors, same columns and headers) — formats are unchanged 1.14 → 1.19.3 for everything below unless noted. **Re-measured on vanilla 1.19.3 (P00, 2026-09-27):** changes are marked "1.19.3" inline — buildings.txt type names, legacy airports/rocketsites, weatherpositions sizes, new state keys and categories, the 4th adjacency pattern.

## map/default.map  [V]
Points the engine at every map file. Vanilla content (keep file names unless you have a reason):
```
definitions = "definition.csv"
provinces = "provinces.bmp"
positions = "positions.txt"
terrain = "terrain.bmp"
rivers = "rivers.bmp"
heightmap = "heightmap.bmp"
tree_definition = "trees.bmp"
continent = "continent.txt"
adjacency_rules = "adjacency_rules.txt"
adjacencies = "adjacencies.csv"
#climate = "climate.txt"
ambient_object = "ambient_object.txt"
seasons = "seasons.txt"
# Define which indices in trees.bmp palette which should count as trees for automatic terrain assignment
tree = { 3 4 7 10 }
```
`positions.txt` is empty (0 bytes) in vanilla.

## map/provinces.bmp  [V][C]
- 24-bit BGR BMP, BITMAPINFOHEADER (40-byte DIB), uncompressed. Vanilla 5632×2048.
- One unique RGB colour per province. No anti-aliasing. `0,0,0` is reserved for the dummy row 0 and does not appear in vanilla's bitmap.
- W and H multiples of 256; W×H ≤ ~13,238,272 [C]. 32-bit files crash: "We do not support bitdepth at 32" [C].
- The map wraps horizontally: column 0 is adjacent to column W-1 [C]; vanilla has no province touching both edges.
- A province may consist of several disconnected pixel groups (488 vanilla provinces do — island groups), but keep them compact (see bounding box, 02-provinces.md).

## map/definition.csv  [V]
`id;r;g;b;type;coastal;terrain;continent` — semicolon separated, no header, latin-1/ASCII safe.
```
0;0;0;0;land;false;unknown;0          <- mandatory dummy row
1;230;81;119;lake;false;lakes;7
4;0;0;232;sea;true;ocean;0
3838;...;land;true;plains;1
```
- `type`: `land` | `sea` | `lake`.
- `coastal`: `true` | `false` — derived, see invariant 5 in SKILL.md.
- `terrain`: a category from `common/terrain/00_terrain.txt` `categories = { }`: land `plains forest hills mountain desert marsh jungle urban`; sea `ocean` (vanilla uses only `ocean` for sea provinces; naval terrain variety comes from strategic regions' `naval_terrain`); lake `lakes`. `unknown` only for row 0.
- `continent`: 1-based index into `map/continent.txt`; 0 for sea. Lakes carry the continent of their surroundings (vanilla: 77 of 125 lakes use 0, 48 use a land continent — both load).
- IDs must be sequential. The file ends with a newline; a trailing empty line is harmless.

## map/continent.txt  [V]
```
continents = {
	europe
	north_america
	south_america
	australia
	africa
	asia
	middle_east
}
```
Each name needs localisation (vanilla keys are the names themselves in `*_l_english.yml`). Continents drive AI areas and some triggers.

## map/adjacencies.csv  [V][C]
Header (required, first line):
`From;To;Type;Through;start_x;start_y;stop_x;stop_y;adjacency_rule_name;Comment`
Terminator (required): `-1;-1;;-1;-1;-1;-1;-1;-1` — in 1.19.3 vanilla it is followed by 2 blank lines and a `#` comment line, so trailing blanks/comments after it are fine.
Blank lines and `#` comment lines between rows are accepted (1.19.3 mod). Types seen: `sea`, `impassable`, empty, `land` (1.19.3 mod); a strait may pass through a **lake** province (1.19.3 mod).

| Pattern (vanilla count) | From/To | Type | Through | Meaning |
|---|---|---|---|---|
| Strait (140; 1.19.3: 148) | land, land | `sea` | **sea** province crossed | army can cross; blocked if the sea is enemy-controlled |
| Canal (3: Panama, Kiel, Suez) | **sea, sea** | `sea` | **land** province the canal runs through | ships pass; gated by `adjacency_rule_name` |
| Blocked border (70; 1.19.3: 93) | land, land | `impassable` | `-1` | removes a pixel adjacency (e.g. across a mountain wall) |
| Rule on a touching sea pair (1.19.3: 7 — Gibraltar N/S, Øresund, Bosphorus, Dardanelles, Hormuz, Otranto) | **sea, sea**, already pixel-adjacent | *(empty)* | `-1` | only attaches `adjacency_rule_name` (strait control); proves nothing about linking non-touching seas (EXP-01) |
| Land link | land, land | *(empty)* | -1 | adds adjacency between non-touching land provinces [C] |
| `river`, `large_river` | land, land | as named | -1 | [C] forces river-crossing type; unobserved in vanilla |

`start_x;start_y;stop_x;stop_y` are pixel coordinates for drawing the crossing arrow (y counted from the bottom); `-1` = auto.

## map/adjacency_rules.txt  [V][S]
```
adjacency_rule = {
	name = "SUEZ_CANAL"
	contested = { army = no navy = no submarine = no trade = no }
	enemy     = { army = no navy = no submarine = no trade = no }
	friend    = { army = yes navy = yes submarine = yes trade = yes }
	neutral   = { army = yes navy = yes submarine = yes trade = yes }
	required_provinces = { 12049 1155 4073 9947 }   # controlling these decides the rule
	is_disabled = { has_global_flag = SUEZ_CANAL_BLOCKED  tooltip = suez_blocked_tt }  # optional
	icon = 12049                 # province where the icon is drawn
	offset = { 1 0 -6 }          # x y z icon offset
}
```
Optional triggers `is_friend`, `is_neutral`, `is_enemy` pick the rule set (evaluation order is documented in the vanilla file header). `name` must be localised.

## map/strategicregions/<id>-<Name>.txt  [V][S]
```
strategic_region={
	id=1
	name="STRATEGICREGION_1"
	provinces={ 221 271 296 ... }
	naval_terrain=water_deep_ocean     # optional, sea regions only: water_deep_ocean | water_shallow_sea | water_fjords
	weather={
		period={
			between={ 0.0 30.0 }        # day.month, both 0-based: Jan 1 .. Jan 31
			temperature={ -6.0 12.0 }
			no_phenomenon=0.500 rain_light=1.000 rain_heavy=0.150 snow=0.200
			blizzard=0.000 arctic_water=0.000 mud=0.300 sandstorm=0.000
			min_snow_level=0.000
		}
		... 12 periods (one per month) in vanilla
	}
}
```
Localisation `STRATEGICREGION_<id>:0 "Name"` in `strategic_region_names_l_english.yml`. `static_modifiers` block optional [S].

## history/states/<id>-<Name>.txt  [V][S]
```
state={
	id=1
	name="STATE_1"                  # localisation key
	manpower = 322900
	state_category = town
	resources={ steel=32 aluminium=35 }     # optional
	history={
		owner = FRA
		controller = FRA              # optional
		victory_points = { 3838 1 }  # province value; repeatable
		buildings = {
			infrastructure = 2
			industrial_complex = 1
			air_base = 1
			3838 = { naval_base = 3 }   # provincial buildings keyed by province id
			# 1.19.3 provincial keys: naval_base, bunker, coastal_bunker, naval_supply_hub,
			# naval_headquarters, naval_facility, land_facility, dam, dam_mountain, landmark_*
		}
		add_core_of = FRA
		1939.1.1 = { owner = GER }    # dated blocks allowed
	}
	provinces={ 3838 9851 11804 }
	local_supplies=0.0              # optional, 0..20
	impassable = yes                # optional
	force_link_ownership_to = 123   # 1.19.3: on all 21 impassable states — owner follows state 123
	impassable_ignored_links = { }  # 1.19.3: seen once; semantics unverified (Tier 3)
	buildings_max_level_factor = 1.0  # optional
}
```
See 03-states.md for semantics. Vanilla file names are `<id>-<Name>.txt`, ASCII; 1.19.3 also ships `<id> - <Name>.txt` and `<id> -<Name>.txt` (all load). VP values may be written as floats (`30.0`). Declare `state_category` once — 4 vanilla states declare it twice and which wins is unknown.

## common/state_category/<name>.txt  [V]
```
state_categories={
	town = {
		local_building_slots = 4
		color = { 200 200 0 }
	}
}
```
Vanilla slots: enclave 0, tiny_island 0, wasteland 0, pastoral 1, small_island 1, **large_island 3 (new in 1.19.x)**, rural 2, town 4, large_town 5, city 6, large_city 8, metropolis 10, megalopolis 12. `large_island`, `small_island` and `tiny_island` also carry a `buildings_max_level = { naval_base = 8 air_base = 6 }`-style block.

## map/buildings.txt  [V] (7 columns; type names re-measured on vanilla 1.19.3)
One line per building **model position**: `state_id;building;x;y;z;rotation;extra`
- `x` = pixel column, `y` = height (~9.5 = sea level), `z` = pixel row **counted from the bottom** of the image, rotation in radians.
- `extra`: for `naval_base_spawn` = the **sea** province the port faces; for `floating_harbor` = the land province it attaches to; otherwise `0`.
- 1.19.3 type set and multiplicities (08-vanilla-baseline.md has counts):
  - per state: arms_factory ×6, industrial_complex ×6, anti_air_building ×3; air_base, synthetic_refinery, radar_station, fuel_silo, `stronghold_network`, `nuclear_reactor_spawn`, `rocket_site_spawn` ×1
  - per land province: bunker, supply_node, `special_project_facility_spawn`
  - per coastal land province: `naval_base_spawn` (column 7 = sea), coastal_bunker, `naval_supply_hub`, `naval_headquarters`, floating_harbor (column 7 = land)
  - per coastal state: dockyard
  - specific states only: `dam_spawn`, `landmark_spawn`, `locks_spawn`
- Older names (1.14.1): `naval_base`, `nuclear_reactor`, `rocket_site` — do not emit them for 1.19.x.
- Generated by the nudger (07-validation.md). Missing positions → models not drawn, or crashes when the building is built (naval base / floating harbour [C]).

## map/unitstacks.txt  [V]
`province;type;x;y;z;rotation;offset` — up to 39 position types (0–38) per province: unit models, VP marker, labels, combat positions, naval positions for sea provinces. Generated by the nudger; 10 MB in vanilla.

## map/weatherpositions.txt  [V]
`strategic_region_id;x;y;z;size` (`small` / `big` in 1.19.3: 136 / 452 of 588 lines) — weather effect anchors, several per region.

## map/airports.txt / map/rocketsites.txt  — LEGACY (absent in 1.19.3)
Vanilla 1.19.3 ships neither file; air base and rocket site positions come from `buildings.txt` (`air_base`, `rocket_site_spawn`). Do not generate them. Old 1.14.1 format for reference:
```
1={3838 }      # state_id={ province }  — where the airbase / rocket site model sits
```
One entry per state.

## map/supply_nodes.txt  [V]
`level province` — vanilla: 713 lines, all level `1`. (A community snippet calls the first number an ID; vanilla shows it is constant 1 — treat it as level.) All vanilla nodes sit on land provinces, 683/713 on railway provinces.

## map/railways.txt  [V]
`level count p1 p2 ... pcount` — each line a railway chain; consecutive provinces must be adjacent (vanilla: 3512 segments, 0 non-adjacent). Levels 1–5 (vanilla uses 1–4).

## map/cities.txt, map/cities.bmp  [V]
`cities.bmp`: 8-bit indexed, same size as provinces; palette index selects a `city_group` in `cities.txt` (e.g. `color_index = 15` western cities) that controls procedural city meshes and density. Decorative only.

## map/colors.txt [V], map/seasons.txt [V], map/ambient_object.txt [V]
Country-independent colour list, seasonal colour grading, and decorative objects. Copy vanilla unless you have a reason; ambient_object positions must be re-placed on a new map (or emptied).

## map/terrain/*.dds  [V]
Texture atlases and colour maps (`colormap_rgb_cityemissivemask_a.dds` is 2816×1024 = half size, water colormaps). Must be regenerated or rescaled for a new canvas (05-rasters.md).

## Localisation files (UTF-8 **with BOM**, `l_english:` first line) [V]
- `state_names_l_english.yml`: ` STATE_1:0 "Corsica"`
- `victory_points_l_english.yml`: ` VICTORY_POINTS_6521:0 "Berlin"` (key = **province** id)
- `strategic_region_names_l_english.yml`: ` STRATEGICREGION_1:0 "Southern England"`
- `province_names_l_english.yml`: optional per-province names.
