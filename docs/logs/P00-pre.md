# P00-pre — local Windows bootstrap (2026-09-27)

Run in plain `claude` (not overwatch) on the owner's PC. P00 was not started.

## Machine facts
| Item | Value |
|---|---|
| OS | Windows 11 Pro 10.0.26200 |
| Bash tool shell | **Git Bash** (`/bin/bash.exe`, `MINGW64_NT-10.0-26200 … Msys`) → POSIX syntax (`$HOI4_GAME_DIR`, `rm -rf`, `sed -i`) works in agent Bash calls |
| PowerShell | Windows PowerShell 5.1.26100 |
| Python command | `python` → `C:\Users\<user>\AppData\Local\Programs\Python\Python312\python.exe`, **3.12.10**, same in Git Bash and PowerShell. (`py -3` → 3.14.5, not used.) The Store stub `WindowsApps\python.exe` is on PATH but *after* the real install, so it is never hit. |
| Python deps | numpy 2.5.3, pillow 12.3.0, scipy 1.18.1, shapely 2.1.2, pyproj 3.8.0, pytest 9.1.1 (+ pyyaml, installed only for the frontmatter check) |
| Claude Code | 2.1.283 |
| Game version | `Operation Postern v1.19.3.0.c01a (5632)`, rawVersion `1.19.3.0` |
| `HOI4_GAME_DIR` | `E:/SteamLibrary/steamapps/common/Hearts of Iron IV` |
| `HOI4_USER_DIR` | `C:/Users/<user>/Documents/Paradox Interactive/Hearts of Iron IV` (Documents not redirected to OneDrive) |
| `HOI4_WORKSHOP_DIR` | `E:/SteamLibrary/steamapps/workshop/content/394360` (54 items) |
| git | core.autocrlf=true, core.longpaths=true, user derprito64bit / 145411741+derprito64bit@users.noreply.github.com |

## Checklist
| Check | Result | Evidence | Fix applied |
|---|---|---|---|
| A1 repo clean, main, up to date | PASS | `git status` clean; `git pull` → already up to date; HEAD `c34e878` = merge commit (parents `feaadd6`, `ebdcb72`) "Merge project foundation…" | — |
| A2 core.longpaths | FIXED | was unset → `true` | `git config core.longpaths true` (repo-local) |
| A3 .gitattributes binary rules | FIXED | `git check-attr -a -- mod/map/provinces.bmp` → `binary: set, diff: unset, merge: unset, text: unset` | added `*.bmp *.dds *.png *.tga *.npy binary`, kept `* text=auto` |
| A4 git identity + push auth | PASS | user.name/email set; `git push --dry-run origin main` → "Everything up-to-date" (no auth prompt) | — |
| A5 worktrees | PASS | `worktree add ../_wt_test -b _wt_test` → `remove` → `branch -D` all succeeded; `worktree list` shows only main | — |
| B1 shell | PASS | Git Bash (MINGW64) | — |
| B2 python ≥ 3.11, not Store stub | PASS | `python` = 3.12.10 real install in both shells | — |
| B3 deps install + import | PASS | single import of all six succeeded | `pip install numpy pillow scipy shapely pyproj pytest` |
| C1 guard offline | PASS | fake Write to `mod/x.txt` → `scope_guard: 'mod/x.txt' is generated output …`, `exit=2` | — |
| C2 guard live | PASS | Write tool on `mod/_hook_test.txt` blocked: `PreToolUse:Write hook error: … scope_guard: 'mod/_hook_test.txt' is generated output …`; hook command unchanged | — (settings.json untouched) |
| C3 workspace trust | PASS | implied by C2 (project hooks run only after trust) | — |
| D1 claude version + agent frontmatter | PASS | 2.1.283; all 12 `.claude/agents/*.md` parse with `yaml.safe_load`, `name` == file name for all; this session's agent registry lists all 12 | — |
| D2 `/agents`, `/hooks` output | PENDING owner | slash commands can't be run by the agent → CHK-010 | — |
| D3 models on plan | PENDING owner | fleet uses opus (code-reviewer, gfx-engineer, history-auditor, overwatch, pipeline-engineer, visual-qa), sonnet (compat-engineer, fact-checker, researcher, state-builder, triage), haiku (validator) → CHK-011 | — |
| E1 game dir | PASS | `hoi4.exe`, `map/provinces.bmp` present at the default path; Steam `libraryfolders.vdf` lists `C:\Program Files (x86)\Steam` and `E:\SteamLibrary` | — |
| E2 user dir | PASS | `[Environment]::GetFolderPath('MyDocuments')` = `C:\Users\<user>\Documents`; folder has `mod/`, `pdx_settings.txt`, `logs/` | — |
| E3 workshop dir | PASS | exists, 54 subscribed items | — |
| E4 settings.local.json | FIXED | `HOI4_USER_DIR` was the `<you>` placeholder; now real path. `git check-ignore` → `.gitignore:6`; not in `git status`. `echo $HOI4_USER_DIR` in the Bash tool already returns the new value (no restart needed) | rewrote file with verified paths |
| E5 game version | PASS | 1.19.3.0 (expected 1.19.x) | — |
| F1 ee_project.py docstring | FIXED | 5 usage lines `python3 …` → `python …`; shebang unchanged | edit |
| F2 P05 hash command | FIXED | `sha256sum …` → portable `python -c "import hashlib…"` one-liner | edit |
| F3 other POSIX-only commands | PASS | grep for `sha256sum`, `rm -rf`, `sed -i`, `ls -la`, `python3 ` in `docs/`, `.claude/agents/`, `CLAUDE.md` → no other hits. Even if any appear later they work, since the Bash tool is Git Bash | — |
| G1 projection selftest | PASS | `selftest ok: forward matches PROJ, inverse round-trips, mask area 11241712 px ~ 11241701, crop ok` | — |
| G2 vanilla validator | PASS | ran to `SUMMARY: 0 errors, 4 warnings {'states': 1081, 'strategic_regions': 304, 'provinces': 13413}` in **16 s**; JSON at `build/p00pre_vanilla.json` (not committed). Interpretation is P00's job | — |
| G3 wu_check list / overlap | PASS | list shows P00, P00b, P00c (todo); overlap → `0 active work units, 0 overlaps`; both exit 0 | — |

## Observations (no action taken)
- Guard messages print `�` instead of `—` because Python writes stderr in the Windows console code page (cp1252). Cosmetic; the block still works. Fixing it means touching `scope_guard.py` (frozen) or adding `PYTHONUTF8=1`/`PYTHONIOENCODING=utf-8` to settings env → CHK-012 for the owner.
- `core.autocrlf=true` + `* text=auto`: text files are CRLF in the working copy and LF in the repo. Harmless for HOI4 text; binaries are now protected by A3.
- `to-check/` already holds files dated 2026-09-28 (written by the cloud session, one day ahead of this machine's clock). This run's file uses the local date 2026-09-27, so it sorts *before* them even though its CHK numbers continue after CHK-009.
- pip 25.0.1 is outdated (26.2.1 available); not required.

## Decisions
- Hook command in `.claude/settings.json` left as is — it runs in this environment (C2).
- No agent files edited.

NEXT_ACTION = P00 (after the owner answers CHK-010/011; neither blocks P00 unless a model alias is missing)
