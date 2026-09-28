# 02 — Provinces: rules, sizing, generation

## 1. What a province is to the engine
- The atomic tile for movement, combat, supply, buildings (provincial), VPs and ownership. States are sets of land provinces; strategic regions are sets of any provinces.
- Adjacency = two provinces sharing a pixel edge (4-neighbourhood; diagonal-only contact is **not** a clean border → avoid, and never create X-crossings) plus the links in `adjacencies.csv`, minus `impassable` pairs.
- Movement cost and combat width come from the terrain category in definition.csv (05-rasters.md for how terrain.bmp relates).
- Province *size* in pixels drives travel time (distance between centres), the number of provinces an army must cross, frontage and AI behaviour. **Province count is gameplay design, not geography.**

## 2. Hard limits
| Limit | Value | Evidence |
|---|---|---|
| Min pixels per province | 8 ("Province X has only Y pixels … Should have at least 8") | [C] error text |
| X-crossings | 0 allowed (MAP_ERROR "Map invalid X crossing") | [C] |
| Bounding box | "TOO LARGE BOX" if pixels are spread too far; exact threshold **unverified**. Vanilla max side: land 280 px, sea 179 px (map W=5632). Validator warns at W/8. Keep land ≤ 250 px and sea ≤ 180 px until tested. | [C] + [V] |
| Province count | Community snippet says "less than 19,000"; **unverified**. Vanilla 13,362. Provisional project budget ≈ 20,000 (PROJECT_SPEC) until EXP-03 measures the real ceiling (OPEN-2). | [C] weak |
| Colour | unique 24-bit RGB; not `0,0,0` | [V] |

## 3. Vanilla calibration (5632×2048, Miller-like, cropped)
- Land provinces 10,104: area px p5 69 / median 161 / p95 1,253 / max 15,697.
- Sea provinces 3,133: p5 1,112 / median 2,330 / p95 3,645 (sea is ~15× coarser than land).
- Lakes 125: median 115 px.
- Density is deliberately uneven: median land province 112–124 px in the rows holding Europe, 216–566 px in the tropics/south.
See 08-vanilla-baseline.md for the full table.

## 4. Density model for the Equal Earth map (this project)
Equal Earth at the project canvas (5120×2304, 60° S crop) gives **45.37 km² per pixel everywhere** (equal-area); land ≈ 2.96 M px.
Because Equal Earth does not inflate high latitudes, Europe gets far fewer pixels than in vanilla, so density is set by an explicit **importance weight**, not by pixel area — and **historical border lines override density**.

Target province area (px) for a land cell:
```
A_target = clamp( A_base / w , A_min , A_max )
A_base, w  = docs/PROJECT_SPEC.md §3 (single source of truth; currently A_base = 200)
A_min      = 30 px (≈ 1,360 km²; ~4× the 8-px floor)
A_max      = 2,000 px and bbox side ≤ BBOX_MAX
```
Border rule: every line of the border overlay (1914 / 1918–1923 / 1936 / 1939, 03-states.md §3.2b) must coincide with province borders; provinces are split along overlay lines even if that makes them smaller than A_target (never below 8 px — merge slivers across the *other* side of the overlay line instead, and log it).
Sea provinces: `A_target_sea = 900–2,500 px` near coasts / in naval theatres, larger in open ocean up to the bbox limit; ring historically important small islands with their own sea provinces so they are identifiable (owner decision DEC-009).

Budget check (before generating, recorded in the phase log):
`density count + overlay splits + sea + lakes + off-globe ≤ PROVINCE_BUDGET` (confirmed by EXP-03).

## 5. Generation algorithm (deterministic, scripted)
1. **Land mask** from coastline polygons rasterised at the canvas (06-equal-earth.md). Resolve 1-px peninsulas/isthmuses: morphological open/close with a 3×3 kernel, then re-add true isthmuses (Panama, Suez, Kra, Corinth) by hand-listed polygons.
2. **Constraint lines**: rasterise the *state* boundaries first (03-states.md). Provinces are generated **inside** each state polygon so no province straddles a state border. Also use major rivers/mountain crests as soft seeds boundaries where available.
3. **Seeds**: Poisson-disk sample each state polygon with radius `r = sqrt(A_target / π) * 1.8`; always seed: every VP city, every port city, every capital.
4. **Grow**: weighted Voronoi / multi-source Dijkstra on the pixel grid where crossing a high-slope or river pixel costs more (so borders follow ridges and rivers). Use 4-connectivity.
5. **Clean**: (a) merge components < A_min into the neighbour with the longest shared border in the same state; (b) remove X-crossings by reassigning one of the four corner pixels to the diagonal neighbour that minimises perimeter; repeat until 0; (c) ensure each province is 4-connected except deliberate island groups; (d) re-check the 8-px minimum.
6. **Islands** (owner decision DEC-009: include them, enlarge only very slightly): an island < 8 px at canvas scale that is inhabited in 1936, named in a sovereignty/colonial list, or militarily significant (Malta, Iwo Jima, Midway, Wake, Pitcairn, Tristan da Cunha…) becomes the **smallest compact blob of 8–10 px** centred on its true position, logged in `data/provenance/island_adjustments.csv` (true area, drawn area); uninhabited rocks without significance are dropped into the surrounding sea (logged too).
7. **Seas**: generate sea provinces with the same algorithm on the sea mask, seeded more densely within 3 px-rings of coasts and around straits; every coastal land province must touch at least one sea province that is not shared with more than ~6 other coastal provinces (ports need a clear sea tile).
8. **Lakes**: lakes ≥ 12 px from the lake dataset become `lake` provinces (impassable). Smaller lakes are dropped (land).
9. **Colours**: assign colours deterministically (e.g. hash of province id → RGB, rejecting duplicates and `0,0,0`); store the mapping in definition.csv only.
10. **IDs**: order land first by state then by row-major centroid, then seas, then lakes, then off-globe filler (06-equal-earth.md). Freeze IDs once states are written; later edits append new IDs.

## 6. Derived fields (always regenerate, never hand-edit)
- `coastal`: land 4-adjacent to sea ⇒ true (vanilla: exact match on all 2,330). Sea touching land ⇒ true.
- `terrain`: majority class of `terrain.bmp` pixels inside the province, mapped through the `terrain = { }` palette table in `00_terrain.txt`, with overrides: province containing a city ≥ threshold population ⇒ `urban`.
- `continent`: from a lookup polygon layer (continent.txt order), sea ⇒ 0.

## 7. Editing an existing province map by hand
- Tools: GIMP/Photoshop with **pencil** tool, anti-aliasing off, no colour management; or HOI4 Province Editor / MapGen [C]. Paint.NET is only safe for provinces.bmp and world_normal [C].
- After any pixel edit: run `validate_map.py` → X-crossings, undefined colours, sub-8-px provinces, coastal flags.
