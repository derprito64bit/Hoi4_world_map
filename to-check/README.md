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
| [2026-09-28_g0-answers.md](2026-09-28_g0-answers.md) | 2026-09-28 (newest) | Gate G0 answers (DEC-029..034), S1–S11 applied, CHK-014 re-run pending |
