# Equal Earth World Map for Hearts of Iron IV

> **Project status: archived / on hold (October 2026).** Development is paused. The project **may or may not be continued** in the future. Nothing here is a playable mod yet; it is the research, tooling and design groundwork for one.

## What this is
An attempt to build a **full-world map mod for Hearts of Iron IV (game version 1.19.x)** drawn in an **Equal Earth–style projection**: countries keep their true relative sizes, unlike the vanilla map, which inflates the high latitudes. It also has to stay **seamless** where the map wraps around in the Pacific, like the vanilla map. The long-term goals were:

- historically accurate 1936 borders, with finer states than vanilla (≈ 1,800–2,500) and ≈ 20,000 provinces;
- borders that can also express the 1914 / 1918–1923 alternative-history lines;
- census-based manpower, cited resources and dense rivers;
- keeping vanilla focus trees and events working through a compatibility layer.

The full plan is in [`docs/PROJECT_SPEC.md`](docs/PROJECT_SPEC.md).

## Where it stopped
Only the groundwork phase (P00) was completed. **No map content (provinces, states, regions) exists yet.**

| Done | Notes |
|---|---|
| Baseline measurements of vanilla 1.19.3 | `docs/logs/P00.md` |
| An **in-game experiment kit** (`tools/experiments/`) and ~30 owner-run tests | results in `to-check/2026-09-28_exp-results.md` |
| A **hybrid Equal Earth projection**: exact Equal Earth in the interior, blending to straight edges for a native seamless wrap | branch `wu/P00d` (`tools/projection/`); reviewed, one small fix outstanding, **not merged**; the band width λb was not yet chosen (60° / 90° / 120°; preview images in `to-check/previews/`) |
| Validator engine-rule checks | branch `wu/P00e`, unfinished and unreviewed |

## Engine findings that may be useful to other HOI4 map modders
These were measured in game (HOI4 1.19.3, with the `-debug` launch option); evidence and dates are in `docs/OPEN_QUESTIONS.md` and the `to-check/` files.

1. **Map-check errors are only written to `error.log` with `-debug`.** Without it, a fatal map error shows only "Failed to load the map".
2. **Strategic-region centre divide-by-zero.** The engine snaps each province's bounding box to a 2-px grid, averages the box centres of a region, and, if that point lies in no member box, divides by `mean.x − (rect_x0 + rect_w/2)`. A zero there crashes the game at load (`EXCEPTION_INT_DIVIDE_BY_ZERO`). Confirmed 6/6 with targeted test maps; a checker is in `tools/experiments/regioncentre.py`.
3. **Naval strategic regions must be one connected piece** of sea pixels, across the wrap included; otherwise there is a fatal `MAP_ERROR … is fractioned`.
4. **`TOO LARGE BOX`** fires when a province's bounding box is **wider than roughly 600–1200 px or taller than roughly 174–300 px**. Area does not matter. It is non-fatal but misplaces unit stacks. A province crossing the left/right wrap seam is measured as full map width.
5. **Province count:** 16k, 20k, 24k and 30k provinces all loaded and played smoothly. A crash seen at 24k was finding 2, not a ceiling.
6. **State IDs must be gap-free** (1..N); a gap crashes the game on scenario start.
7. Provinces of **≤ 8 px** are logged (non-fatal). **Adjacency rows across the wrap seam** crash the game (`sea` type) or are measured the long way round. **Lake provinces next to sea** trap fleets.
8. Canvases above ≈ 13.2 M px (5632×2560, 6144×2560) crashed; 5120×2304 loads and plays. `trees.bmp` works at 2:1 and 3:1.

## Repository layout
| Path | Contents |
|---|---|
| `docs/PROJECT_SPEC.md` | master plan and fixed parameters |
| `docs/AGENT_SYSTEM.md`, `.claude/agents/`, `.claude/agentops/` | the Claude Code multi-agent setup used to run the project (orchestrator + specialists, scope-enforcing hook, review loop) |
| `.claude/skills/hoi4-map-modding/` | HOI4 map-modding reference notes, an offline map validator (`scripts/validate_map.py`) and the Equal Earth canvas helper |
| `docs/prompts/` | phase prompts P00–P14 |
| `docs/logs/`, `docs/reviews/`, `docs/visual-qa/`, `docs/board/` | phase logs, code reviews, visual reviews, the work-unit board |
| `to-check/` | owner decisions, in-game test results, screenshots, previews (dated batches) |
| `tools/experiments/`, `tests/` | the in-game experiment kit and its tests |
| `assets/` | camera-define and shader-patch variants used in one experiment |

## Using the tools
Python 3.11+ with `numpy pillow scipy shapely pyproj`. You need your own copy of Hearts of Iron IV: the tools read game files from your install at build time, and **no Paradox game files are included in this repository**. Copy `.claude/settings.local.json.example` to `.claude/settings.local.json` and set your paths. Examples:
- `python .claude/skills/hoi4-map-modding/scripts/validate_map.py "<HOI4 install>" --json build/vanilla.json`
- `python tools/experiments/build.py all --check` (builds the experiment mods into `build/`, which is gitignored)
- `python -m pytest -q tests`

## Credits and notes
- Equal Earth projection: Šavrič, Patterson & Jenny (2018). The preview coastlines (branch `wu/P00d`) use Natural Earth data (public domain), downloaded at build time and not committed.
- Hearts of Iron IV is © Paradox Interactive. This is an unofficial fan project, not affiliated with or endorsed by Paradox. In-game screenshots in `to-check/screenshots/` are test captures.
- Much of the code and documentation was produced with Claude Code (Anthropic) under the owner's direction; commits co-authored by Claude are marked as such.
- **License:** none has been chosen yet, so default copyright applies (all rights reserved by the owner) until a license file is added.
