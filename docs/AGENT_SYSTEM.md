# Agent system — Equal Earth HOI4 map

A fleet of Claude Code subagents with one orchestrator, one writer per work unit,
measured feedback loops and hook-enforced write scopes. Design lessons borrowed
from OpenFlow (github.com/Vasiniks/OpenFlow): single writer, specs and reports on
disk, measurement tools instead of opinions, capped critic loops, permissions
enforced by config rather than prose, no extra personas without a distinct job.

## 1. Roster
| Agent | Model | Writes (hook-enforced) | Job | May call |
|---|---|---|---|---|
| **overwatch** (main session: `claude --agent overwatch`) | opus, effort high | `docs/logs/**`, `docs/board/work_units.json`, `docs/OPEN_QUESTIONS.md`, `to-check/**`; plus owner-approved edits to `CLAUDE.md`, `docs/PROJECT_SPEC.md`, `docs/AGENT_SYSTEM.md`, `docs/prompts/**`, `.claude/skills/**`, `.claude/agents/**` | plans work units, dispatches, runs the loop, merges to `main`, stops at owner gates | all below |
| **researcher** | sonnet | `data/research/**` | finds + extracts primary evidence, tiered, with falsification attempts | — |
| **state-builder** (worktree) | sonnet | `data/states/**`, `data/provenance/**`, `data/research/**`, `data/countries/**` | one country/region per WU: geometry, splits/merges, attributes, provenance | researcher |
| **pipeline-engineer** (worktree) | opus | `tools/**`, `tests/**`, `requirements.txt`, `data/README.md`, `data/manifest.csv`, `.gitignore` | all generator code; the only code writer | — |
| **compat-engineer** (worktree) | sonnet | `tools/compat/**`, `tests/compat/**`, `data/compat/**` | vanilla 1.19.x compatibility: ID mapping + override generator | researcher |
| **gfx-engineer** (worktree) | opus | `assets/gfx/**`, `assets/common/defines/**`, `tests/gfx/**` | shader overrides + camera/graphics defines for a seamless look; colour-only effects | — |
| **code-reviewer** | opus | `docs/reviews/**` | adversarial review of generator/compat/gfx diffs | — |
| **fact-checker** | sonnet | `docs/factchecks/**` | verifies 100 % of claim rows: source exists, supports the claim, right date, right tier, country status | — |
| **visual-qa** | opus | `docs/visual-qa/**` | looks at rendered previews and owner screenshots; seams, edges, slivers, island placement, shape vs. source | — |
| **history-auditor** | opus, effort xhigh | `docs/audits/**` | adversarial audit of historical claims; PASS/FAIL for G2/G4 | — |
| **validator** | haiku | `build/**` | runs deterministic checks, reports counts and deltas | — |
| **triage** | sonnet | `docs/board/triage/**` | the feedback looper: dedupes/ranks all findings, trend + regression detection, MERGE/FIX/BLOCK | — |

Why these models (Anthropic price per MTok in/out: Fable 5.1 $10/$50, Opus 5.5 $4/$20, Sonnet 5 $2/$10, Haiku 4.5 $1/$5):
- **Opus** where a mistake cascades or judgment is the product: orchestration, generator code (high blast radius), code review, history adjudication.
- **Sonnet** for high-volume, well-specified work with a checker behind it: per-country state building, research extraction, compat mapping, triage.
- **Haiku** for running commands and summarising numbers.
- **Fable 5.1** is not assigned by default (≈2.5× Opus). Use it ad hoc for a blocked adjudication by running `claude --model fable` or overriding the model on a single Agent call.
Aliases (`opus`, `sonnet`, `haiku`) resolve to the current generation; pin full IDs in the frontmatter if you need reproducibility.

Hard enforcement (not prompts):
- `.claude/settings.json` → PreToolUse hook `.claude/agentops/scope_guard.py` blocks Write/Edit outside each agent's scope (`.claude/agentops/scopes.json`), blocks hand edits of generated `mod/**` for everyone, and blocks subagents from editing `.claude/**`, `CLAUDE.md`, the spec and prompts.
- Overwatch's project-file access is granted via `agent_exceptions` in `scopes.json` (owner decision 2026-09-30); `.claude/agentops/**` and `.claude/settings.json` stay owner-only.
- Files created through Bash are caught at merge: `python .claude/agentops/wu_check.py diff <WU>` must pass before overwatch merges.
- Concurrency ≤ 6 subagents, spawn depth ≤ 2 (settings env).

## 2. Branching and commits
- `main` is the integration branch (Claude Code worktrees branch from the default branch, so it must be `main`).
- Every writer runs in its own worktree on `wu/<WU-id>`; commits there only.
- Overwatch merges with `git merge --no-ff wu/<id>` after the loop passes; gates are tagged `gate-G<n>`.
- Read-only agents write their reports in the main checkout; overwatch commits them with the merge (`docs(<WU>): review/audit/triage r<n>`).
- No PR per WU (hundreds of them). The owner reviews at gates via the gate report in `docs/logs/` and the chat.

## 3. The loop (per WU)
```
dispatch (overwatch) ─► builder/engineer commits on wu/<id>
      ▲                         │
      │                         ▼
 FIX (≤3 rounds)          validator (numbers)  ─┐
      │                         │               │
      │   code-reviewer (tools/assets) · fact-checker (all data rows) · history-auditor (history sample) · visual-qa (map output)
      │                         │               │
      └──────────── triage (ranked P0/P1/P2, trend, regression) ─► MERGE / BLOCK
```
- P0/P1 → re-dispatch the same agent with the triage list only. P2 → logged, no loop.
- Converged = validator GREEN + 0 P0/P1 → `wu_check diff` → merge.
- Two rounds with no improvement or a new ERROR code → REGRESSION → revert the round's commit on the WU branch and retry once; else BLOCK and ask the owner (entry in the newest `to-check/` file).

## 4. Work-unit board (`docs/board/work_units.json`)
```json
{ "id": "P04-EU-POL", "phase": "P04", "title": "Poland 1936 states",
  "agent": "state-builder", "scope": ["data/states/europe/POL*", "data/provenance/states_POL.csv", "data/research/POL/**"],
  "depends_on": ["G1"], "status": "todo|in_progress|review|changes_requested|done|blocked",
  "branch": "wu/P04-EU-POL", "attempts": 0, "notes": "" }
```
WU `scope` must also list the **generated outputs** a WU commits (e.g. `mod/map/provinces.bmp`), because `wu_check.py diff` checks the whole diff; the hook still forbids hand-editing them — generators write them through Bash.
Unit granularity: P04/P06 per **country** (big countries split: USSR per republic/oblast group, China per province group, British India per presidency/agency, USA per census region); generators per **phase step**.
`python .claude/agentops/wu_check.py overlap` must be 0 before dispatching.

## 5. Running it (CLI on the owner's PC)
1. Install Claude Code, Python 3.11+ (on PATH as `python`), Git (Git for Windows includes Git Bash).
2. Clone the repo, `pip install -r requirements.txt` (after P01), copy `.claude/settings.local.json.example` → `.claude/settings.local.json` and fix the paths.
3. Accept the workspace-trust prompt (needed for hooks).
4. `claude --agent overwatch`, then paste the phase prompt from the chat.
5. Watch the board: `python .claude/agentops/wu_check.py list`.

## 6. What is deliberately not here
No per-file writers, no separate "planner" and "architect" personas, no auto-merge without the validator, no agent that edits the agent system itself.
