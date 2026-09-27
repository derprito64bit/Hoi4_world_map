# 06 — Equal Earth canvas for this project

## 1. Projection (Šavrič, Patterson & Jenny 2018)
```
A1 = 1.340264   A2 = -0.081106   A3 = 0.000893   A4 = 0.003796   M = √3/2
θ = asin(M · sin φ)
x = λ · cos θ / ( M · (A1 + 3A2θ² + 7A3θ⁶ + 9A4θ⁸) )
y = θ · (A1 + A2θ² + A3θ⁶ + A4θ⁸)
```
Unit sphere extents: |x| ≤ 2.70663 (equator at λ = ±180°), |y| ≤ 1.31736 (poles). Aspect of the outline ≈ **2.0546 : 1**. Poles are lines (flat top/bottom), sides are curved.
`scripts/ee_project.py` implements forward + Newton inverse; its `selftest` checks against PROJ 9 (`+proj=eqearth`) to 1e-6 and round-trips 20k random points. Always use it (or PROJ) — never re-derive by hand.

## 2. Canvas decision (recommended defaults — confirm at Gate G0)
| Parameter | Recommended | Why |
|---|---|---|
| W × H | **5120 × 2560** | multiples of 256; area 13,107,200 ≤ 13,238,272 ceiling; largest 2:1 canvas that fits |
| Fit | equator spans the full width (scale 945.826 px/rad) | the left and right image edges are both the cut meridian, so the game's horizontal wrap joins the Pacific at the equator |
| Vertical | outline height 2,492 rows, 34-row off-globe margin top and bottom | full ±90° globe incl. Antarctica |
| Central meridian lon0 | **10.9° E** → cut at **169.1° W** | measured on Natural Earth 50 m land: the cut meridian that crosses the least land north of 60° S (0.16°, only St Lawrence Island, Alaska); all of Chukotka, Wrangel, Fiji, Tonga, Samoa, Chatham stay on the east (Asian/Oceanian) edge, Alaska on the west edge |
| Resolution | 45.37 km²/px (≈ 6.74 km side), 14.22 px per degree of longitude at the equator | |
| Alternative | 4608 × 2304 (56.0 km²/px) | if the province budget or performance tests fail |

Land pixel budget at 5120×2560 (Natural Earth 50 m countries, geodesic areas): Asia 686k, Africa 659k, North America 535k, "Europe" incl. all of Russia 506k, South America 388k, Antarctica 272k, Oceania 187k — ≈ 3.23 M land px total.

## 3. Off-globe area (pixels outside the outline, ≈ 1.87 M px)
The engine needs every pixel to belong to a province. Recommended treatment (OPEN-3, confirm in game):
- Fill with **lake** provinces (impassable to armies and fleets), each ≤ the bbox limit, in dedicated strategic regions `Off-globe N/S/E/W`, in no state, continent 0, terrain `lakes`.
- heightmap = 89 (water), terrain index 15, rivers 254, colormap a flat dark tone so it reads as "outside the world".
- Ensure no sea province touches an off-globe lake along a long border in a way that creates coastal flags; lakes don't set coastal flags (vanilla rule: only `sea` does), so this is safe.
Fallback if lakes misbehave: impassable wasteland land provinces in `impassable = yes` states owned by nobody.

## 4. The wrap seam
- Columns 0 and W-1 are adjacent in game. With the equator-fit, only rows near the equator have on-globe pixels at both edges; they must be **the same geographic meridian** (they are: lon0 ± 180°).
- Provinces must not straddle the seam (keep each province wholly on one side; vanilla has none crossing).
- Pacific connectivity away from the equator: add seam links between sea provinces that face each other across the cut (same latitude band) — see 04 §2 "Wrap-seam links" and OPEN-1.
- Islands on the cut (St Lawrence Island at 50 m; check the 10 m dataset for Diomedes etc.): assign each whole island to the side holding the larger part, shift the rest by 360°, log in `data/provenance/island_adjustments.csv`.

## 5. Coordinate conventions
- Image (numpy/PIL): row 0 = north (top). BMP files store rows bottom-up; Pillow handles that.
- Game coordinates in buildings.txt/unitstacks.txt: `x = column`, `z = H − row` (from the bottom). `Canvas.to_game_xz` does this.
- Always rasterise polygons in canvas space (project vertices, then fill) after **densifying** edges (≤ 0.25° segments) — straight lon/lat edges are curves in Equal Earth.

## 6. Consequences to design for
- Equal-area: Europe, Japan, Korea get much less space than in vanilla; the tropics, Africa, South America and Antarctica get more. Density weights (02-provinces.md §4) compensate for gameplay; they do not change geography.
- Shapes near the outline edges (Alaska, Chukotka, New Zealand, Siberia's east) are sheared. That is correct for the projection; do not "fix" it.
