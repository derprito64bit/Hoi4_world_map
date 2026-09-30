# 2026-09-30 — Projection decision: hybrid Equal Earth (seamless wrap)

Follows `2026-09-28_exp-results.md` (in-game results EXP-01..09). Evidence: `docs/logs/P00b.md` §24, `docs/logs/P00d.md`.

## Decision
| ID | Decision | Consequence | Status |
|---|---|---|---|
| DEC-035 (Q-012) | Owner, 2026-09-30: **option 4, hybrid projection**. Equal Earth in the interior, blending smoothly to straight map edges in a band on both sides of the Pacific seam, so every row reaches both edges and the map wraps seamlessly like vanilla. | Replaces pure Equal Earth as `PROJECTION`. No off-globe area on the canvas → Q-009 (seam sea corridors) and Q-010 (off-globe filler) are **superseded** once the design is approved. The band is not equal-area (the Pacific rim at high latitudes is stretched E–W). The design and band width get an owner choice from previews (CHK-019). | DONE (decision); design in WU P00d |

## Still owner decisions (after the previews)
| ID | Question | Status |
|---|---|---|
| Q-013 | Band width: how much of the world stays pure Equal Earth (interior half-width λb). Candidates rendered in P00d: 60°, 90°, 120° from lon0 (a wider interior = stronger stretch in the band). | OPEN → CHK-019 |
| Q-014 | Top edge: in EXP-09b/c the top rows sat under the game's map frame. With the hybrid, the 90° N line spans the full width. Options: a larger top camera distance only, or rows of top margin on the canvas (changes `CANVAS`/`LAT_RANGE` layout). P00d reports what fits. | OPEN |
| Q-011 | BBOX_MAX: keep 250/180 (recommended) or relax to width ≤ 600 / height ≤ 173. | OPEN |
| — | LON0 stays 10.9° E (seam at 169.1° W) unless the previews show a better seam; P00d reports sensitivity. | — |

## Project-file changes to apply after Q-013 (S14; `.claude/**`, `CLAUDE.md`, `docs/PROJECT_SPEC.md` and `docs/prompts/**` are owner / plain-session only)
| # | File | Change |
|---|---|---|
| S14a | `docs/PROJECT_SPEC.md` §2 `PROJECTION` | "Equal Earth" → "Hybrid Equal Earth (DEC-035): EE interior within λb of lon0, smooth C¹ blend to straight edges at ±180°; seamless wrap" + band parameters; `CANVAS`/`LAT_RANGE` note on the top margin per Q-014 |
| S14b | `docs/PROJECT_SPEC.md` §11 | drop the off-globe fade/filler goal; keep the camera/top-edge items; wrap seam = native pixel contact |
| S14c | `.claude/skills/hoi4-map-modding/references/06-equal-earth.md` | §1: add the hybrid definition; §3 off-globe area: "none with the hybrid"; §4 wrap seam: native; §6: the distortion band |
| S14d | `.claude/skills/hoi4-map-modding/scripts/ee_project.py` | replace/extend with the approved `tools/projection/hybrid.py` (or make it import it); keep the `selftest`/`info` commands |
| S14e | `.claude/agents/*.md`, `docs/prompts/P03..P14` | wherever they say off-globe filler / lake provinces / seam corridors / Equal Earth mask → hybrid canvas (full rectangle) |
| S14f | `CLAUDE.md` commands | the projection self-test command, if the helper moves |

## Checks
| ID | Check | Who | Status |
|---|---|---|---|
| CHK-019 | Look at the P00d preview images (coastlines + graticule, a distortion heat map, a key-place table) for λb 60/90/120 vs plain Equal Earth and pick one | owner | OPEN (after P00d) |
| CHK-020 | Overwatch project-file access granted (scopes.json agent_exceptions; agentops/settings stay owner-only) | owner/plain session | DONE (2026-09-30, merge of chore/overwatch-scope) |

## Engine rules from P00b that stay valid for any projection
- Province bbox: width < ~600–1200 px and height < ~174–300 px, else TOO LARGE BOX (non-fatal, misplaces units); spec 250/180 is safe.
- No province may cross the wrap seam (it is measured as full width).
- Every naval strategic region must be pixel-contiguous (incl. across the wrap), else a fatal MAP_ERROR.
- Region-centre guard `regioncentre.guard_failures` = 0 for every build (the 2-px grid divide-by-zero rule, confirmed 6/6).
- State IDs contiguous 1..N (a gap is fatal).
- Provinces ≥ 9 px (≤ 8 px is logged).
- Adjacency links across the seam are useless (measured unwrapped) or crash (`sea` type) → seam crossings must be native pixel contact, which the hybrid provides.
- Canvas ≤ ~13.2 M px (both larger variants crashed); 5120×2304 loads and plays.
