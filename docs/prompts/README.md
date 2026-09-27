# Phase prompts — how to use

Each file is a complete, copy-paste task specification for one agent session.
They follow the structure in the project's prompt guide:
Objective → Scope/Frozen → Context → Constraints (hard / preference / discretion) → Decision rules → Failure modes → Workflow → Verification → Deliverables → Stop condition & checkpoint.

| File | Phase | Needs before start | Gate after |
|---|---|---|---|
| `P00-setup-and-parameters.md` | inspect install, confirm parameters | nothing | G0 (owner) |
| `P01-tooling.md` | repo scaffolding, build runner, provenance checker | G0 | — |
| `P02-data-acquisition.md` | download + manifest of geodata | P01 | — |
| `P03-canvas-and-masks.md` | land/sea/lake/off-globe masks, draft heightmap | P02 | G1 |
| `P04-state-geometry.md` | start-date state polygons + provenance (one run per continent) | G1 | G2 (audit A1) |
| `P05-provinces.md` | province generation, provinces.bmp, definition.csv | G2 | G3 |
| `P06-state-files.md` | history/states, categories, manpower, VPs, localisation | G3 | G4 (audit A1) |
| `P07-strategic-regions.md` | regions + weather + region localisation | G4 | — |
| `P08-adjacencies.md` | straits, canals, impassable, seam links, rules | P07 | — |
| `P09-rasters.md` | terrain, rivers, heightmap final, normal, trees, cities, colormaps | P08 | — |
| `P10-positions-supply.md` | buildings, unitstacks, airports, rocketsites, weatherpositions, supply nodes, railways | P09 | — |
| `P11-packaging.md` | descriptor, replace_path, vanilla stubs, localisation completeness | P10 | G5 |
| `P12-ingame-verification.md` | owner-run debug load + agent fix loop | G5 | G6 (owner) |
| `A1-adversarial-map-audit.md` | independent auditor for G2/G4 (and any time) | any | — |
| `A2-boundary-research-audit.md` | research one disputed/uncertain boundary | any | — |

Rules for whoever runs these:
- Run one phase per session. Paste the whole file. Fill `{{…}}` placeholders first.
- P04 may run as parallel sessions, one per continent, in separate git worktrees (they write disjoint files: `data/states/<continent>.geojson`, `data/provenance/states_<continent>.csv`). Everything else runs sequentially.
- Auditor sessions (A1) must be a different session from the one that produced the work.
