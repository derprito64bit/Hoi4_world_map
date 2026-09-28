# 2026-09-27 — local Windows setup (P00-pre)

Follows `2026-09-28_self-audit.md` (that file carries a later date from the cloud session's clock; numbering continues from CHK-009). Full evidence: `docs/logs/P00-pre.md`.

## Open checks for the owner
| ID | What to do | Why | Status |
|---|---|---|---|
| CHK-010 | In a Claude Code session in this repo, run `/hooks` and paste the output. Expect a PreToolUse entry with matcher `Write\|Edit\|MultiEdit\|NotebookEdit` running `scope_guard.py`. Optionally also `/agents` (or confirm the 12 project agents appear when starting `claude --agent overwatch`). | The agent can't run slash commands. The hook already blocked a live write to `mod/` and the session's agent registry lists all 12 agents, so this is confirmation only. | DONE (2026-09-28): owner's `/hooks` shows 1 hook configured, PreToolUse: 1 hook |
| CHK-011 | Run `/model` and report which of Opus / Sonnet / Haiku your plan offers. | Fleet uses `opus` (code-reviewer, gfx-engineer, history-auditor, overwatch, pipeline-engineer, visual-qa), `sonnet` (compat-engineer, fact-checker, researcher, state-builder, triage), `haiku` (validator). A missing alias affects those agents; the owner decides how to remap. | DONE (2026-09-28): `/model` offers Opus 5.5 (default), Sonnet 5, Haiku 4.5, and Fable 5.1 (needs usage credits) — all fleet aliases available |
| CHK-012 | Decide whether to fix the `�` shown instead of `—` in scope_guard messages (Windows cp1252 stderr). Option: add `"PYTHONUTF8": "1"` to the `env` block of `.claude/settings.local.json` (also makes `open()` default to UTF-8 for all project Python). | Cosmetic; blocking works. `scope_guard.py` is frozen, so not changed here. | DONE (2026-09-28): `"PYTHONUTF8": "1"` added to the `env` block of the shared `.claude/settings.json` (applies on every machine; project scripts already pass explicit encodings) |
| CHK-013 | Optional: turn off the Store stub (Settings → Apps → Advanced app settings → App execution aliases → both *python* entries off). | `WindowsApps\python.exe` is on PATH after the real Python 3.12, so it is never used today; disabling it removes the risk if PATH order changes. | OPEN (optional) |

## Verified on this machine (no action)
Git Bash is the Bash-tool shell; `python` = 3.12.10 in both shells; deps installed; game 1.19.3.0 at `E:/SteamLibrary/steamapps/common/Hearts of Iron IV`; user dir `C:/Users/<user>/Documents/Paradox Interactive/Hearts of Iron IV`; workshop `E:/SteamLibrary/steamapps/workshop/content/394360`; push auth works; worktrees work; hook fires.
