# 2026-09-28 — self-audit of prompts, skill and agents

Owner asked for a full review of the agents and a fact-check of every prompt against the latest data (plan + HOI4 formats). Evidence used: vanilla 1.14.1 files (public mirror), a mod built for **1.19.3** (Kaiserreich, public GitHub — formats only, nothing else read), Claude Code docs for subagents and hooks, HOI4 patch notes / news for 1.17–1.19.

## Findings and fixes
| ID | Finding | Evidence | Fix | Status |
|---|---|---|---|---|
| SA-001 | Map file formats are unchanged 1.14 → 1.19.3 | the 1.19.3 mod's map (13,950 provinces, 1,125 states, 275 regions) passes the validator with 0 errors after SA-002/003 | recorded in skill 01-file-formats | DONE |
| SA-002 | **Validator bug**: ignored `replace_path`, merging vanilla folders into a mod → 964 false duplicate-state errors | reproduced on the 1.19.3 mod | validator now honours `descriptor.mod` replace_path | DONE |
| SA-003 | Validator too strict on adjacencies: rejected blank/`#` comment lines, type `land`, straits through a lake | all present in the 1.19.3 mod | accepted (lake strait = warning) | DONE |
| SA-004 | Skill said `world_normal.bmp` must be 24-bit | the 1.19.3 mod ships 32-bit | skill + validator accept 24 or 32 | DONE |
| SA-005 | Skill missed **coal**, a state resource since 1.17 (No Compromise, No Surrender; drives the energy/factory limit) | patch notes / news | skill 03-states, P06, P00 updated; P00 confirms the key list | DONE |
| SA-006 | `replace_path` still valid in 1.19.3 descriptors (`history/states`, `map/strategicregions`, `map/supplyareas`) | 1.19.3 mod descriptor | CHK-004 partly answered; P00 confirms on the owner's install | DONE (Tier 2) |
| SA-007 | Validator had one bbox limit for land and sea | spec has 250 / 180 | new `--bbox-limit-sea`; vanilla has a 280-px land province that loads → 250 is conservative | DONE |
| SA-008 | 13 prompts (P01–P12, A1, A2) predated the canvas change, 1.19, the fleet and the skeleton-first plan | sweep | all rewritten with work-unit tables, agents, scopes and checks | DONE |
| SA-009 | Two prompts told pipeline-engineer to write provenance CSVs its hook would block | automated prompt-vs-scope cross-check | reclassified as generated outputs; cross-check now 0 issues | DONE |
| SA-010 | A1 audit wrote to `docs/logs/`, outside history-auditor's scope | cross-check | now `docs/audits/` | DONE |
| SA-011 | overwatch and triage both allowed to write `docs/board/triage/**` | scopes.json | overwatch narrowed to `work_units.json` | DONE |
| SA-012 | Researcher called from a state-builder worktree had no rule for where to write | agent review | writes inside the caller's checkout path | DONE |
| SA-013 | `python3` commands fail on many Windows installs | owner runs Windows CLI | all docs use `python` | DONE |
| SA-014 | P00 board entry said branch `wu/P00` but P00 commits on `main` | board | fixed | DONE |
| SA-015 | Generated outputs committed by a WU must be listed in its scope or `wu_check diff` fails | AGENT_SYSTEM §4 | rule added | DONE |

## Still unverified (need the owner's 1.19.3 install or an experiment)
| ID | Item | Where it gets answered |
|---|---|---|
| UV-001 | exact 1.19.3 vanilla numbers (state count ≈ 1,081 per MapChart, province counts, building multiplicities, unitstack types) | P00 |
| UV-002 | `gfx/FX/constants.fxh` map constants and camera defines in 1.19.3 | P00 → EXP-08/09 |
| UV-003 | province-count ceiling, bbox threshold, 8-px minimum, trees aspect, state-ID gaps, seam links, off-globe filler | EXP-01..07 |
| UV-004 | DDS sizes/formats in 1.19.3 | P00 |
