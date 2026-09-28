# 11 — Rendering: camera, shaders, map edges, limits

Evidence: [V] vanilla defines — **re-measured on 1.19.3 at P00** (`docs/logs/P00.md` §5); [C] community (search snippets); **UNVERIFIED** items need an experiment.

## 1. What the engine does (and does not do)
- The map is a flat terrain mesh displaced by `heightmap.bmp`, textured from `terrain.bmp` + `map/terrain/*.dds`, wrapped horizontally. There is **no built-in projection, globe mode or zoom-dependent geometry warp**. [V/C]
- Every gameplay position (province pixels, `buildings.txt`/`unitstacks.txt` coordinates, mouse picking, icons, arrows) is defined on the pixel grid. Any per-zoom geometric distortion done in a shader would desynchronise visuals from picking/icons → not viable. Map projection must be baked into the bitmaps by our pipeline (06-equal-earth.md).
- What can change with zoom: colours and opacities. Vanilla already fades province/state borders and map-mode overlays with camera distance (`PROVINCE_BORDER_FADE_NEAR/FAR = 200/300`, `STATE_BORDER_FADE_NEAR/FAR = 400/500`, `GRADIENT_BORDERS_CAMERA_DISTANCE_OVERRIDE_*`), hides VP names by distance (`VICTORY_POINT_MAP_ICON_TEXT_CUTOFF = {150, 250, 500}`), railways above `RAILWAY_CAMERA_CUTOFF = 300` (1.19.3). [V]

## 2. Defines to review for a new canvas (`common/defines/00_graphics.lua` unless noted) [V]
Namespaces matter: an override must use the namespace the game file uses (`NDefines.NFrontend.CAMERA_MAX_HEIGHT = …`).

| Define | Namespace | Vanilla 1.19.3 | Why it matters here |
|---|---|---|---|
| `CAMERA_OUTSIDE_MAP_DISTANCE_TOP` / `_BOTTOM` | NGraphics | 200.0 / 200.0 | how far past the top/bottom edge the camera may move — reduce so the player never sees beyond the map; tune with the 14-row margins |
| `CAMERA_MIN_HEIGHT` / `CAMERA_MAX_HEIGHT` | **NFrontend** | 50.0 / 3000.0 | max zoom-out: at 3000 the whole map (and the off-globe corners) is visible; lowering it hides corners but limits overview |
| `CAMERA_ZOOM_SPEED`, `CAMERA_ZOOM_KEY_SCALE`, `CAMERA_ZOOM_SPEED_DISTANCE_MULT` | NGraphics | 50, 0.02, 6.0 | feel only |
| `CAMERA_LOOKAT_X/Y/Z`, `CAMERA_START_X/Y/Z`, `CAMERA_END_X/Y/Z` | **NFrontend** | 2958/0/1519, 2958/800/1400, 2958/900/1400 | main-menu camera positions **in vanilla map coordinates** (≈ Central Europe) — must be recomputed with `Canvas.to_game_xz` for the new map or the menu shows the wrong place |
| `CAMERA_SPEED_IN_MENUS`, `CAMERA_INTERPOLATION_SPEED` | NFrontend | 0.1, 0.19 | menu feel only |
| `STRATEGIC_REGION_ZOOM_HEIGHT` | NGraphics | 300.0 | only if the new scale makes icons crowd |
| `PROVINCE_BORDER_FADE_NEAR/FAR`, `STATE_BORDER_FADE_NEAR/FAR` | NGraphics | 200/300, 400/500 | border fades by zoom |
| `RAILWAY_CAMERA_CUTOFF` | NGraphics | 300.0 | railways hidden above this height |
| `VICTORY_POINT_MAP_ICON_TEXT_CUTOFF` | NGraphics | {150, 250, 500} | VP names by zoom |
| `MAP_ICONS_*_CAM_DISTANCE` | NGraphics | group 90, state group 180, strategic 350 | icon grouping by zoom |
| `MINIMUM_PROVINCE_SIZE_IN_PIXELS` | NGraphics | 8 | vanilla comment: smaller provinces only produce an error.log line and make the game unplayable to click; gameplay unaffected. Our hard floor (EXP-04, folded into EXP-03) |
| `MAP_SCALE_PIXEL_TO_KM` | **NGame** (`00_defines.lua`) | 7.114 (= 40,075 km / 5,632 px) | tied to the vanilla canvas; **override to 6.74** for 5120×2304 (area-mean km per px side, owner decision Q-003) in P14 |

## 3. Shaders (`gfx/FX/`) [C]
- Mods can override files in `gfx/FX/` (`.fx`, `.fxh`); visual overhaul mods (e.g. Texture Overhaul) do this.
- `gfx/FX/constants.fxh` (1.19.3, P00): `MAP_NUM_TILES` 4 × `TEXELS_PER_TILE` 512 = 2048 = the terrain texture atlas side (`ATLAS_TEXEL_POW2_EXPONENT` 11) — atlas constants, **not** map size; `WATER_HEIGHT` 9.5 = sea level; the rest are camera-distance fades (`SNOW/MUD/ICE/FOW_CAM_*`, `FOG_BEGIN/END`, `TERRAIN_WATER_CLIP_*`).
- The map size is **not** a constant in any shader file: `MAP_SIZE_X/Y` and `FOW_POW2_X/Y` are used in `pdxmap.shader`, `maparrow.shader`, `fow.fxh`, `standardfuncsgfx.fxh` (incl. wrap handling `± MAP_SIZE_X`) but defined nowhere under `gfx/FX` → injected by the engine from the loaded map. So `constants.fxh` **probably needs no change** for a new canvas; EXP-08 confirms visually.
- Map-relevant shaders: `pdxmap.shader` (terrain), `pdxwater.shader`, `border.shader`, `river.shader`, `tree.shader`, `maparrow.shader`, `strait.shader`, `mapname.shader`, `sky.shader`, `traderoute.shader`.
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
1. ~~Measure vanilla 1.19 camera defines + `constants.fxh` (P00).~~ Done 2026-09-27 (§2, §3).
1b. Override `NGame.MAP_SCALE_PIXEL_TO_KM = 6.74` (Q-003).
2. Compute menu camera coordinates for the new map (`Canvas.to_game_xz`) — look at the capital of the player's default start region.
3. Tune `CAMERA_OUTSIDE_MAP_DISTANCE_*` and `CAMERA_MAX_HEIGHT` with owner screenshots (EXP-09).
4. Implement the smallest shader change that achieves the edge look; A/B screenshots at 5 zoom levels; owner approves.
