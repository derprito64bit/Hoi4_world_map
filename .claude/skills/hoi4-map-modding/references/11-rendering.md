# 11 — Rendering: camera, shaders, map edges, limits

Evidence: [V] vanilla 1.14.1 defines; [C] community (search snippets); **UNVERIFIED** items need P00 measurement or an experiment.

## 1. What the engine does (and does not do)
- The map is a flat terrain mesh displaced by `heightmap.bmp`, textured from `terrain.bmp` + `map/terrain/*.dds`, wrapped horizontally. There is **no built-in projection, globe mode or zoom-dependent geometry warp**. [V/C]
- Every gameplay position (province pixels, `buildings.txt`/`unitstacks.txt` coordinates, mouse picking, icons, arrows) is defined on the pixel grid. Any per-zoom geometric distortion done in a shader would desynchronise visuals from picking/icons → not viable. Map projection must be baked into the bitmaps by our pipeline (06-equal-earth.md).
- What can change with zoom: colours and opacities. Vanilla already fades province/state borders and map-mode overlays with camera distance (`PROVINCE_BORDER_FADE_NEAR/FAR = 200/300`, `STATE_BORDER_FADE_NEAR/FAR = 400/500`, `GRADIENT_BORDERS_CAMERA_DISTANCE_OVERRIDE_*`), hides VP names by distance (`VICTORY_POINT_MAP_ICON_TEXT_CUTOFF = {150, 250, 500}`), railways above `RAILWAY_CAMERA_CUTOFF = 200`. [V]

## 2. Camera defines to review for a new canvas (`common/defines/00_graphics.lua`, NGraphics) [V]
| Define | Vanilla 1.14.1 | Why it matters here |
|---|---|---|
| `CAMERA_OUTSIDE_MAP_DISTANCE_TOP` / `_BOTTOM` | 200.0 / 200.0 | how far past the top/bottom edge the camera may move — reduce so the player never sees beyond the map; tune with the 14-row margins |
| `CAMERA_MIN_HEIGHT` / `CAMERA_MAX_HEIGHT` | 50.0 / 3000.0 | max zoom-out: at 3000 the whole map (and the off-globe corners) is visible; lowering it hides corners but limits overview |
| `CAMERA_ZOOM_SPEED`, `CAMERA_ZOOM_SPEED_DISTANCE_MULT` | 50, 6.0 | feel only |
| `CAMERA_LOOKAT_X/Z`, `CAMERA_START_X/Y/Z`, `CAMERA_END_X/Y/Z` | 2958/1519, 2958/800/1400, 2958/900/1400 | main-menu camera positions **in vanilla map coordinates** (≈ Central Europe) — must be recomputed with `Canvas.to_game_xz` for the new map or the menu shows the wrong place |
| `STRATEGIC_REGION_ZOOM_HEIGHT`, weather/railway/icon cutoffs | various | only if the new scale makes icons crowd; revisit after in-game tests |

## 3. Shaders (`gfx/FX/`) [C]
- Mods can override files in `gfx/FX/` (`.fx`, `.fxh`); visual overhaul mods (e.g. Texture Overhaul) do this. `gfx/FX/constants.fxh` contains map constants such as `MAP_NUM_TILES`, `TEXELS_PER_TILE`, `WATER_HEIGHT`. **UNVERIFIED** whether they must be changed for a non-vanilla canvas — P00 reads them from 1.19.x and compares with the canvas; EXP-08 tests.
- Viable shader techniques for the off-globe area (all colour-only, so gameplay stays aligned):
  1. **Edge vignette**: in the terrain/water pixel shader, sample an "off-globe mask" (e.g. encoded in a spare channel of a colormap, or a dedicated texture) and blend towards a styled ocean/paper colour; strength can depend on camera height so the curved edge is soft at close zoom and reads as a clean map edge when zoomed out.
  2. **Water continuation**: make off-globe pixels render exactly like open ocean (same water shader, heightmap 89, colormap ocean tone) so the rectangle corners look like more sea; combine with (1) at far zoom.
  3. **Seam blending at the wrap**: nothing needed if both edges are the same meridian (they are, 06 §4) — verify colormap/normal continuity across column 0 ↔ W-1.
- Shader overrides break easily across game patches; keep them minimal, in `assets/gfx/FX/**`, with a diff against the vanilla file of the targeted version recorded in `docs/logs/P14.md`.

## 4. Limits to design around
- Area ceiling ~13.24 M px [C] (stay ≤ unless EXP-08 passes). Width and height multiples of 256.
- Very large provinces or sea zones → "TOO LARGE BOX" (EXP-02).
- No per-province zoom LOD beyond vanilla's fades; tiny provinces become hard to click when zoomed out — density model should keep ≥ 30 px outside deliberate cases.

## 5. Checklist for P14
1. Measure vanilla 1.19 camera defines + `constants.fxh` (P00).
2. Compute menu camera coordinates for the new map (`Canvas.to_game_xz`) — look at the capital of the player's default start region.
3. Tune `CAMERA_OUTSIDE_MAP_DISTANCE_*` and `CAMERA_MAX_HEIGHT` with owner screenshots (EXP-09).
4. Implement the smallest shader change that achieves the edge look; A/B screenshots at 5 zoom levels; owner approves.
