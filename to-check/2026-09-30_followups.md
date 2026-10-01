# 2026-09-30 — Follow-ups from the in-game tests (approval needed)

Follows `2026-09-30_projection-decision.md`. Overwatch may now edit project files, **but only for items approved here** (rule in `.claude/agents/overwatch.md`). Each item says what changes and why.

## Questions for the owner
| ID | Proposal | Evidence | Recommendation | Status |
|---|---|---|---|---|
| Q-015 (S15) | Update `docs/PROJECT_SPEC.md` §2 with the test results: `PROVINCE_BUDGET` "provisional, must be confirmed by EXP-03" → **confirmed ≈ 20,000** (16k–30k play smoothly; land share +6–12 % more pixels under the hybrid); `MIN_PROVINCE_PX` hard floor **8 → 9** (≤ 8 px is logged); `BBOX_MAX` "until EXP-02" → the measured rule (width < 600–1200, height < 174–300; keep 250/180 per Q-011); drop "off-globe" from the budget split (DEC-035) | `2026-09-28_exp-results.md` | approve (Q-011's answer decides the BBOX numbers) | OPEN |
| Q-016 (S12 + S13) | Teach the skill and the map checker the new engine rules: (a) `validate_map.py` ERROR `REGION_CENTRE_DIV0` (the 2-px grid rule, ported from `tools/experiments/regioncentre.py`); (b) ERROR `SEA_REGION_FRACTIONED` (naval regions contiguous across the wrap, from `tools/experiments/naval.py`); (c) ERROR `PROVINCE_CROSSES_SEAM`; (d) WARN at ≤ 8 px instead of < 8; (e) the TOO LARGE BOX per-side rule in `references/02-provinces.md` / `07-validation.md`; (f) "run in-game tests with -debug" in the skill's testing notes. Done as a pipeline-engineer WU for the code (the validator lives in `.claude/skills/…/scripts/`, so overwatch applies the final file move), with tests, then a vanilla re-run (0 ERROR expected) | P00b logs §13–23 | approve: without (a)–(c) the real map could ship the exact crashes we found | OPEN |
| Q-017 | Disk cleanup: 11 finished agent worktrees under `.claude/worktrees/` use **8.0 GB** (mostly test builds). Remove the 10 that are merged (`git worktree remove`; their branches stay in git), and keep P00d's until it is merged. `build/` (1.9 GB) can be rebuilt any time with `build.py`; also delete `build/cache_backup/` | `du -sh` 2026-09-30 | approve (nothing unique is lost: all their commits are on `main`) | OPEN |

## Not needing approval (overwatch did these)
- Board: P00d status corrected to `in_progress` (it was paused, not in review).
- `docs/OPEN_QUESTIONS.md`: results table for OPEN-1..10 + NEW-1..3.
- `to-check/README.md`: index updated.
