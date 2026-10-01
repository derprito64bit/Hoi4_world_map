# to-check — owner decisions and pending checks

Separate from the main docs on purpose. One file per batch, named `YYYY-MM-DD_<topic>.md`, never rewritten after the fact — later batches add a new file and reference the old item IDs.

Item IDs:
- `DEC-###` decision the owner made (with date)
- `EXP-##` in-game experiment the owner runs (agents build the test mod, the owner loads it and reports)
- `CHK-###` something to verify later (by agents or the owner)
- `Q-###` open question waiting for the owner

Status values: `OPEN`, `DONE (date, evidence)`, `CHANGED (see <file>#<id>)`, `DROPPED (reason)`.

| File | Date | Contents |
|---|---|---|
| [2026-09-27_decisions-and-checks.md](2026-09-27_decisions-and-checks.md) | 2026-09-27 | first batch of owner decisions, EXP-01..07, open checks |
| [2026-09-28_rendering-countries-canvas.md](2026-09-28_rendering-countries-canvas.md) | 2026-09-28 | countries rule, 5120×2304 canvas, rendering limits, EXP-08/09, experiment limitations, new agents, build strategy |
| [2026-09-28_self-audit.md](2026-09-28_self-audit.md) | 2026-09-28 | self-audit of prompts/skill/agents against 1.19.3 evidence: 15 fixes, 4 items still unverified |
| [2026-09-27_local-setup.md](2026-09-27_local-setup.md) | 2026-09-27 (local clock, written after the 09-28 files) | P00-pre local Windows setup, CHK-010..013 |
| [2026-09-27_p00-baseline.md](2026-09-27_p00-baseline.md) | 2026-09-27 (local clock) | P00 results: 1.19.3 baseline, engine limits, renderer facts, Q-003..Q-008 for Gate G0 |
| [2026-09-28_g0-answers.md](2026-09-28_g0-answers.md) | 2026-09-28 | Gate G0 answers (DEC-029..034), S1–S11 applied, CHK-014 re-run pending |
| [2026-09-28_p00b-kit.md](2026-09-28_p00b-kit.md) | 2026-09-28 | experiment kit: run order, what to send back, CHK-014..017 |
| [2026-09-28_exp-results.md](2026-09-28_exp-results.md) | 2026-09-28..30 | all in-game results EXP-01..09 + probes, Q-009..Q-012 |
| [2026-09-30_projection-decision.md](2026-09-30_projection-decision.md) | 2026-09-30 | DEC-035 hybrid projection, Q-013/Q-014, S14 change list, CHK-019/020 |
| [2026-09-30_prompt-overwatch-scope.md](2026-09-30_prompt-overwatch-scope.md) | 2026-09-30 | the prompt used to grant overwatch project-file access (CHK-020, done) |
| [2026-09-30_followups.md](2026-09-30_followups.md) | 2026-09-30 | S12/S13/S15 spec, skill and validator updates from the test results; disk cleanup (Q-015..Q-017) |
| [2026-10-01_archive.md](2026-10-01_archive.md) | 2026-10-01 (newest) | project parked/archived: the publication safety check and the resume plan |
