# AUDIT A1: Adversarial audit of {{SCOPE}} (Gate {{GATE}})

> **Revision pending (2026-09-27):** written before the owner's decisions (4608×2048 canvas with 60° S crop, 1.19.x, vanilla compatibility, border overlay, agent fleet). The spec and agent files are authoritative where they differ; this prompt will be refreshed and sent in chat before its phase runs.

You are the **auditor**, not the author. Your incentive is to find regressions, broken invariants and unsupported claims. You make **no changes** to map data; you write a report.

## 1. OBJECTIVE
Decide whether {{SCOPE}} (e.g. "P04 europe polygons", "P06 state files, low-confidence + 10 % sample") may pass Gate {{GATE}}, by independently re-checking invariants and a sample of geographic claims against primary sources.

## 2. SCOPE & BOUNDARIES
- Read: everything. Write only `docs/logs/A1-{{GATE}}-{{SCOPE_SLUG}}.md`.
- FROZEN: all other files. Do not fix what you find.

## 3. CONTEXT
- Rules being audited: `.claude/skills/hoi4-map-modding/SKILL.md` §3–5, `references/03-states.md` §3 & §5, the phase prompt that produced the work (`docs/prompts/PXX-*.md`).
- The producing agent's log is an **assertion, not evidence**. Re-open the underlying files and sources yourself.

## 4. EVIDENCE POLICY
- Tier 1 historical admin/sovereignty sources outrank everything; Tier 2 modern boundaries count only with proof of no change; Tier 3 atlases are weak; Tier 4 (wikis, forums, other mods, vanilla HOI4 shapes) = leads only.
- For every sampled claim, first try to **falsify** it: search for a boundary change, a renaming, a different capital/VP city location, a population figure that contradicts the manpower.
- "Could not verify after checking X, Y" is a valid outcome — record it as UNRESOLVED, not as pass.

## 5. PROCEDURE
1. Re-run deterministic checks yourself: `validate_map.py`, `tools/check_provenance.py`, the phase's `--check` mode. Record exit codes and counts.
2. Sample: all `confidence=low`/UNRESOLVED items + a seeded random 10 % (seed = the commit short-hash as an integer) of the rest.
3. For each sampled item, fill the table below. Open the cited source feature/sheet; don't trust the citation string.
4. Spot-check geometry: overlay the polygon/state on the source for 5 items; compute IoU where both are vectors.
5. Look for systematic errors (a whole country using modern borders; seam-side mistakes; manpower copied from vanilla — compare against vanilla numbers to detect copying).

## 6. REQUIRED DELIVERABLE
`docs/logs/A1-{{GATE}}-{{SCOPE_SLUG}}.md`:
| ID | Claim (what the data asserts) | Cited source (tier) | Falsification attempt | Finding | Severity (HIGH/MED/LOW) | Confidence |
|---|---|---|---|---|---|---|
Then: deterministic check results; systematic issues; verdict **PASS / FAIL** with the rule: any HIGH → FAIL; > 5 % MED in the sample → FAIL.

## 7. STOP CONDITION
Stop when every sampled item has a disposition. Commit only the report: `audit(a1): {{GATE}} {{SCOPE_SLUG}} — PASS|FAIL`. Do not start the next phase.
