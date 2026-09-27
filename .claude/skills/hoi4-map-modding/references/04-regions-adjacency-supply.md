# 04 — Strategic regions, weather, adjacencies, canals, supply, railways

## 1. Strategic regions
- Every province (land, sea, lake) belongs to exactly one region. Vanilla: 288 regions — 134 land-only, 57 sea-only, 54 land+lake, 41 sea regions that also hold 1–3 small-island land provinces (plus one 34/34 mixed region), 1 lake-only, 1 empty.
- Regions define air zones, naval zones, weather and naval terrain. Land-region median 43 provinces (max 279), sea-region median 23 (max 92).
- **States never cross regions** (vanilla: 0 violations). Tiny island states with no land region nearby may sit inside a sea region (vanilla precedent).
- Sizing rule for this project: land regions ≈ 25–60 land provinces, sized so air missions (range ~ hundreds of km) make sense; sea regions follow historical naval theatres and oceanographic basins, 10–60 provinces.
- Borders: follow climate zones and physical barriers first (weather must be homogeneous within a region), then state borders (never cutting a state).
- `naval_terrain` (sea regions): `water_deep_ocean`, `water_shallow_sea`, `water_fjords` — choose from bathymetry (shelf < 200 m → shallow) and coastline type.

### Weather
- 12 `period` blocks (one per month) with `between={ d.m d.m }` (0-based day.month), `temperature={ min max }` °C, and weights for `no_phenomenon rain_light rain_heavy snow blizzard arctic_water mud sandstorm`, plus `min_snow_level`.
- Derive from climate normals (e.g. monthly mean min/max temperature and precipitation of the region centroid, 1931–1960 normals if available, otherwise 1961–1990): snow weight ∝ precipitation share on days < 0 °C; sandstorm only in hot deserts; arctic_water only for sea regions with sea ice.
- Southern-hemisphere regions have inverted seasons — do not copy northern templates.
- `weatherpositions.txt`: 3–8 anchors per region, spread inside it.

## 2. Adjacencies (map/adjacencies.csv)
- **Straits** (land–land through sea): used where two land provinces are separated by one narrow sea province and armies historically could cross. Vanilla's 140 straits include Bosphorus, Kerch Strait, Calabria–Sicily, Skåne–Sjælland (Øresund), the Danish belts, Tsugaru Strait, Java–Sumatra, Sakhalin–Siberia, Orkney–Thurso, Sardinia–Corsica, Tobago–Trinidad and many island-chain hops (Kurils, Carolines, Lesser Antilles). No vanilla comment names an English Channel crossing (checked by comment text only). `Through` = the sea province crossed. Use vanilla's list as the checklist of candidate crossings, then verify each against the new geometry.
- **Canals** (sea–sea through land): Suez, Panama, Kiel pattern: `From`,`To` = the sea provinces at each end, `Through` = land province, `adjacency_rule_name` = rule controlling passage.
- **Impassable** (land–land, Through -1): remove pixel adjacency across mountain walls/glaciers where historically impassable.
- Coordinates: `-1` for auto unless the arrow renders badly.
- Every rule named in the csv must exist in `adjacency_rules.txt` and be localised.

### Wrap-seam links (Equal Earth specific)
Only pixels touching the left and right image edges wrap. With the Equal Earth outline, the edges are on-globe only near the equator, so Pacific sea provinces at higher latitudes on the left and right outline do **not** touch. They must be connected with sea–sea adjacencies. **No vanilla precedent exists for a sea–sea link without a land `Through` (OPEN-1).** Test in game first: (a) `sea` type with a sea `Through`; (b) empty type; pick the one that gives naval pathing and supply without a canal icon.

## 3. Supply (1.11+ system)
- `supply_nodes.txt`: `1 <province>` per starting supply hub. Place in state capitals / railway junctions / major ports; vanilla 713 hubs for 969 states. Every hub must be on a land province in a state, ideally on a railway.
- Capitals of countries get a hub automatically [C] — still list them explicitly.
- Naval supply: coastal provinces with naval bases act as supply entry points; ensure each coastal state that historically had a port has a naval_base in history.

## 4. Railways (map/railways.txt)
- Line format `level count p1..pn`. Consecutive provinces must be adjacent (pixel or adjacency link). Vanilla levels: 1 (448 lines), 2 (409), 3 (28), 4 (7).
- Build from a historical railway dataset at the start date: rasterise lines, map to the province sequence along the line, collapse repeats, split lines at junctions. Level from traffic/gauge importance: trunk mainlines 3–4, secondary 2, branches 1.
- Every supply hub should be connected to its country capital by rail if it was historically.
- Railways never cross sea provinces except over canal/strait adjacency links that are real rail bridges/ferries (verify).

## 5. Checks
`validate_map.py` covers: region membership (every province once), states within one region, railway adjacency, supply-node placement, adjacency rules exist, strait/canal `Through` types. Weather sanity (12 periods, weights ≥ 0, southern-hemisphere seasonality) is manual (P08 prompt).
