# AUDIT A1: Adversarial audit of {{SCOPE}} (gate {{GATE}})

Executed by the **history-auditor** agent (dispatched by overwatch); never by the agent that produced the work.

## 1. OBJECTIVE
Decide whether {{SCOPE}} (e.g. "P04-W wave 1 — Europe", "P06 attributes for FRA/BEL/NLD") may pass gate {{GATE}} by re-checking invariants and a sample of historical claims against primary sources.

## 2. SCOPE
Read everything. Write only `docs/audits/{{GATE}}-{{SCOPE_SLUG}}.md`. Do not fix anything.

## 3. INPUTS
Rules audited: `.claude/skills/hoi4-map-modding/SKILL.md` §3–5, `references/03-states.md` §3 and §5, PROJECT_SPEC `COUNTRIES`, the phase prompt of the work. The builder's log, provenance and the fact-checker's report are **assertions** — reopen the sources yourself.

## 4. EVIDENCE POLICY
Tier 1 (legal acts, gazetteers, national historical GIS, period censuses) > Tier 2 (modern admin data with proof of no change) > Tier 3 (atlases, scholarship). Tier 4 = leads only. Other mods (explicitly Kovas' States Rework) and vanilla HOI4 are never evidence. Try to falsify every sampled claim first. "Could not verify after checking X, Y" = UNRESOLVED, not PASS.

## 5. PROCEDURE
1. Re-run: `validate_map.py`, `tools/check_provenance.py`, the phase `--check`; record exit codes.
2. Sample: every `confidence=low` / UNRESOLVED / Tier 3 item + seeded random 10 % of the rest (seed = integer of the commit short hash) + every country-status row.
3. Per item: open the cited feature/sheet; test date fit; look for a boundary change, renaming, status change (e.g. annexation) between source date and 1936-01-01.
4. Geometry spot-check: overlay 5 states on their sources (`tools/preview.py states --overlay`), IoU where both are vectors.
5. Systematic issues: modern borders across a whole country; values identical to vanilla (copy detection); seam-side mistakes.

## 6. DELIVERABLE `docs/audits/{{GATE}}-{{SCOPE_SLUG}}.md`
| ID | Claim | Cited source (tier) | Falsification attempt | Finding | Severity (HIGH/MED/LOW) | Confidence |
Then deterministic results, systematic issues, verdict: any HIGH → **FAIL**; > 5 % MED in the sample → **FAIL**; else **PASS**.

## 7. STOP
Every sampled item has a disposition. Reply with verdict, counts and the path.
