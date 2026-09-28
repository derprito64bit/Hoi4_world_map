# EXP-09: edge-look variants (P00c)

Goal (DEC-021): the off-globe area of the 5120×2304 Equal Earth canvas should look as seamless as vanilla while you move and zoom. The engine can't warp geometry, so every variant changes only camera limits or colours, and each variant adds exactly one behaviour over an earlier one.

P00b builds one test mod per variant (`EXP-09a` … `EXP-09e`) from `variants.json`:
- **defines**: copy each listed `.lua` into the mod's `common/defines/` under its own basename. The `zz_` prefix sorts after vanilla `00_*.lua` / `01_*.lua`, so the overrides win. The files use `NDefines_Graphics.<Namespace>.<KEY>`. `NDefines.<Namespace>.<KEY>` works equally, because vanilla `00_graphics.lua` copies every `NDefines_Graphics` table into `NDefines`.
- **shader_patches**: apply the listed files in list order, and each file's entries in file order. For each entry, read the vanilla file named in `file` from `$HOI4_GAME_DIR` and write the result to the same relative path in the mod. Modes: `before` inserts `text` just before `anchor`, `after` inserts it just after, `replace` replaces the anchor. Each anchor must occur exactly once when it is applied, otherwise the build fails. The repo never contains vanilla shader text.
- **Patch files**: each file declares one `behaviour`. `offglobe_mask.patch.json` has behaviour `none`: it only defines the shared helper functions and has no visible effect. It must come first. `offglobe_noice` and `offglobe_fade` each work on top of it alone or together, in either order.
- The `experiments/` folders are kit inputs, not mod content. A general "copy `assets/` into `mod/`" step must skip them.

## Variants
| id | adds (one behaviour) | values |
|---|---|---|
| a | nothing: P00b's filler only (lake provinces, heightmap 89, ocean colormap tone) | vanilla: outside-map 200/200, max height 3000 |
| b | camera stops at the map's top/bottom edge | `NGraphics.CAMERA_OUTSIDE_MAP_DISTANCE_TOP/BOTTOM = 15.0` (the 14.3-row off-globe margin, rounded up) |
| c | b + smaller maximum zoom-out | `NFrontend.CAMERA_MAX_HEIGHT = 2400.0` (first calibration point, −20 %) |
| d | c + no sea ice outside the globe outline (`offglobe_mask` + `offglobe_noice`) | 8-px band outside the outline |
| e | d + far-zoom darkening outside the outline (`+ offglobe_fade`) | water darkens to 45 % of its own colour over a 40-px band. The fade starts at camera height 400 and is full at 1500. |

Why ice comes before darkening: ice only shows below camera height 350 (vanilla `ICE_CAM_MIN/MAX` 100/350), while the darkening starts at 400. So c vs d isolates the ice change, and d vs e isolates the darkening.

How d and e work: the shader computes the outline from the Equal Earth formula, with the same constants as `ee_project.py`. It is not a texture, so P00b doesn't need to deliver anything extra. The patch only acts when the loaded map is exactly 5120×2304, and does nothing on any other map size. Only the water pixel colour changes; land, borders, icons and mouse picking stay the same.

## Owner test sheet (same save for every variant, 1920×1080 or state the resolution)
Start a game (any country), pause, map mode default (political). Take each screenshot in each variant unless the row names specific variants.

| # | where | camera | compare | what "good" looks like |
|---|---|---|---|---|
| 1 | Pacific, centred on the wrap seam (Bering Strait / date line) | fully zoomed out (scroll out until it stops) | a / b / c / d / e | a: note how much empty space shows above and below the map. c: less or none. e vs d: the off-globe lens shapes left and right of the seam read as a calm, darker frame with a soft edge, not a hard line. |
| 2 | same place | medium (about half-way: provinces visible, states labelled) | c, d, e | no visible "rectangle corner"; in e the darkening is weak or just starting |
| 3 | same place | close (individual provinces clickable) | c, d, e | off-globe water looks like open sea: no seam, no colour step. e looks identical to d here. |
| 4 | top edge over the Arctic (north of Greenland) | drag the camera as far north as it goes, medium zoom | a vs b | a: the camera drifts far past the edge. b: it stops about at the pole line; the top edge is not a band of empty void. |
| 5 | bottom edge, south of Cape Horn (60° S cut) | drag as far south as it goes, medium zoom | a vs b | same as 4 for the bottom edge |
| 6 | the seam at high latitude: Chukchi Sea / Bering Strait, about 65–75° N. Take one shot on each side of the seam (Chukotka side and Alaska side). | date Jan–Mar; fully zoomed in (camera below about 100, where vanilla ice is at full strength) | **c vs d** (the only difference is the ice change) | c: note any sea ice on the off-globe water beyond the outline. d: no ice beyond the outline; real sea ice on the globe side unchanged. If c shows no ice on the off-globe water at all (e.g. no snow in the filler's weather), the check is **inconclusive**, not a pass: say so. |
| 7 | any | zoom in and out fast, then pan fast across the seam | d vs e | no flicker, no popping band at the outline, frame rate as in a |

Also report for each variant: the `error.log` / `system.log` lines mentioning `pdxwater`, `shader` or `defines` (d and e must add no shader compile errors), and whether province hover/click near the outline still selects the right province.

## Tuning from the screenshots
- **CAMERA_MAX_HEIGHT**: from screenshot 1 in c, measure the fraction `f` of the screen height the map covers, from the top edge to the bottom edge of the map. If `f < 1` (void still visible), try `2400 × f` next. If `f ≥ 1` but the overview feels cramped, go back towards 3000. The camera's field of view isn't exposed in any game file, so this has to be measured.
- **CAMERA_OUTSIDE_MAP_DISTANCE_TOP/BOTTOM**: if the camera cannot centre on the pole line or 60° S in b, raise it (e.g. 50). The floor is **15** (the 14.3-row margin rounded up): below that the camera could no longer reach the pole line / 60° S cut, and `tests/gfx` rejects it. If void still shows at medium zoom at 15, the lever is `CAMERA_MAX_HEIGHT` or the shader fade, not this define.
- **Fade (e)**: all four knobs are literals in `offglobe_fade.patch.json`: band width `40.0`, camera range `400.0, 1500.0`, darkness `0.45`. Too strong means raise the darkness value towards 1 or raise 400; too weak means lower it.

## Known risks
- The camera limits apply to the camera's own travel, not to what is on screen. When zoomed out, the tilted camera can still show some space past the edge. c is the lever for that.
- Vanilla `pdxwater.shader` allows sea ice only above 74 % of the map height (`vMapLimitFade`). On this canvas that line is at 35.8° N, not in the Arctic. This isn't part of EXP-09; it's flagged for P14 (winter screenshots of the Black Sea / Caspian / Yellow Sea would show it).
- The vanilla day/night terminator (`CalcGlobeNormal`) assumes vanilla latitudes, so its shape will be slightly off on this projection. It's cosmetic; P14.
- Shader overrides break on game patches. `tests/gfx` checks the anchors against the installed game (1.19.3) only when `HOI4_GAME_DIR` is set; otherwise those tests are skipped. P00b's build is the hard guard: it fails loudly if an anchor is missing or not unique. P00b should use the same `apply_patch` semantics as `tests/gfx/test_exp09.py`.
