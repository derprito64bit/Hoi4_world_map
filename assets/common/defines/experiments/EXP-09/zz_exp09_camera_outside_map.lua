-- EXP-09 (P00c) variant b and later: limit how far the camera may travel past the top/bottom map edge.
-- Install into the test mod's common/defines/ under this basename; "zz_" sorts after vanilla 00_*.lua / 01_*.lua,
-- so these assignments run after NDefines_Graphics has been built by 00_graphics.lua.
-- Namespace checked against vanilla 1.19.3 common/defines/00_graphics.lua: NDefines_Graphics = { ... NGraphics = { ... } }.

-- Vanilla 1.19.3: 200.0. Canvas 5120x2304 (ee_project.py info): the Equal Earth globe ends 14.3 rows below the top
-- edge (90N pole line) and 14.3 rows above the bottom edge (60S cut). Past those rows there is only lake filler and
-- then nothing, so 200 lets the camera wander ~186 rows into empty space. 15.0 = the margin rounded up: the camera can
-- still centre on the pole line / 60S cut, but not beyond.
NDefines_Graphics.NGraphics.CAMERA_OUTSIDE_MAP_DISTANCE_TOP = 15.0

-- Vanilla 1.19.3: 200.0. Same reasoning for the 60S bottom edge (14.3 margin rows).
NDefines_Graphics.NGraphics.CAMERA_OUTSIDE_MAP_DISTANCE_BOTTOM = 15.0
