# Phase prompts — how to use

Each file is a complete, copy-paste task specification for one agent session.
They follow the structure in the project's prompt guide:
Objective → Scope/Frozen → Context → Constraints (hard / preference / discretion) → Decision rules → Failure modes → Workflow → Verification → Deliverables → Stop condition & checkpoint.

| File | Phase | Needs before start | Gate after |
|---|---|---|---|
| `P00-setup-and-parameters.md` | inspect the 1.19.x install, measure engine limits, confirm parameters | nothing | — |
| `P00b-experiment-kit.md` | build test mods EXP-01..09 for the owner (EXP-09 shader/camera part = WU P00c, gfx-engineer) | P00 | G0 (owner, with EXP results) |
| `P01-tooling.md` | repo scaffolding, build runner, provenance checker | G0 | — |
| `P02-data-acquisition.md` | download + manifest of geodata | P01 | — |
| `P03-canvas-and-masks.md` | land/sea/lake/off-globe masks, draft heightmap | P02 | G1 |
| `P04-state-geometry.md` | P04-S skeleton states + tag list; P04-W per-country refinement waves (+ 1914/1918/1939 overlay) | G1 | G2 per wave (history-auditor) |
| `P05-provinces.md` | province generation, provinces.bmp, definition.csv | G2 | G3 |
| `P06-state-files.md` | history/states, categories, manpower, VPs, localisation | G3 | G4 (audit A1) |
| `P07-strategic-regions.md` | regions + weather + region localisation | G4 | — |
| `P08-adjacencies.md` | straits, canals, impassable, seam links, rules | P07 | — |
| `P09-rasters.md` | terrain, rivers, heightmap final, normal, trees, cities, colormaps | P08 | — |
| `P10-positions-supply.md` | buildings, unitstacks, airports, rocketsites, weatherpositions, supply nodes, railways | P09 | — |
| `P11-packaging.md` | descriptor, compat overrides + assets in place, country history for new tags, localisation completeness, `--install` | P13b, P14 | G5 |
| `P13-vanilla-compat.md` | P13a vanilla state/province mapping (before P06); P13b script remapping (after P10) | G3 / P10 | — |
| (P14, prompt written when due) | rendering: camera defines, shader edge treatment, constants.fxh (gfx-engineer) | P13b | — |
| `P12-ingame-verification.md` | owner-run debug load + agent fix loop | G5 | G6 (owner) |
| `A1-adversarial-map-audit.md` | independent auditor for G2/G4 (and any time) | any | — |
| `A2-boundary-research-audit.md` | researcher resolves one UNRESOLVED boundary / status item | any | — |

Build order (PROJECT_SPEC §12, approved): P00 → P00b/P00c → G0 → P01 → P02 → P03 → G1 → skeleton pass (P04-S → P05 → P13a → P06 → P07 → P08 → P09 → P10 → P13b → P14 → P11 → P12) → refinement waves (P04-W → P05 split → P13a → P06 → P07 → rebuild → P12), Europe first.

Prompts are delivered in chat when their phase is due; the files here are reference copies. Run them in the CLI as `claude --agent overwatch` (see `docs/AGENT_SYSTEM.md`).

Rules for whoever runs these:
- Run one phase per session. Paste the whole file. Fill `{{…}}` placeholders first.
- Parallelism is handled by overwatch: P04 is split into per-country work units run by state-builder agents in isolated worktrees (max 6 at once, disjoint scopes checked by `wu_check.py overlap`).
- Audits (A1) are run by the `history-auditor` agent, never by the agent that produced the work.
