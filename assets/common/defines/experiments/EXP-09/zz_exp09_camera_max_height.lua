-- EXP-09 (P00c) variant c and later: cap the maximum zoom-out height.
-- Install into the test mod's common/defines/ under this basename (sorts after vanilla 00_*.lua / 01_*.lua).
-- Namespace checked against vanilla 1.19.3 common/defines/00_graphics.lua: CAMERA_MAX_HEIGHT lives in NFrontend, not NGraphics.

-- Vanilla 1.19.3: 3000.0 (for the 5632x2048 vanilla canvas). At 3000 the whole map height and the empty space past the
-- top/bottom edges are on screen. 2400.0 (-20 %) is a first calibration point, not a final value: the map camera's
-- field of view is not exposed in any game file, so the height at which the void disappears must be measured.
-- Refinement rule (README.md): at max zoom-out, if the map covers a fraction f < 1 of the screen height, the next
-- value to try is 2400 * f; if the overview feels too cramped, go back towards 3000.
NDefines_Graphics.NFrontend.CAMERA_MAX_HEIGHT = 2400.0
