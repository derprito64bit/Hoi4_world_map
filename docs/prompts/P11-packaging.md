# TASK P11: Packaging, vanilla-breakage stubs, localisation completeness

> **Revision pending (2026-09-27):** written before the owner's decisions (4608×2048 canvas with 60° S crop, 1.19.x, vanilla compatibility, border overlay, agent fleet). The spec and agent files are authoritative where they differ; this prompt will be refreshed and sent in chat before its phase runs.

## 1. OBJECTIVE
Make `mod/` a loadable mod: a correct `descriptor.mod` with `replace_path`s, minimal country/unit history consistent with the new states, stubs that neutralise vanilla content referencing old state/province IDs, and complete localisation — verified by the validator and a static reference scan.

## 2. SCOPE & BOUNDARIES
- Active scope: `mod/descriptor.mod`, `mod/history/countries/**`, `mod/history/units/**`, `mod/common/**` only where needed to neutralise vanilla references (see §5), `mod/localisation/english/**`, `tools/scan_vanilla_refs.py`, `docs/logs/P11.md`.
- FROZEN: every `mod/map/**` file and `mod/history/states/**` (report issues; don't fix here).

## 3. CONTEXT
- What breaks and how: `.claude/skills/hoi4-map-modding/references/10-mod-integration.md` §2–4 (replace_path list, grep patterns, localisation rules).
- Country tags: `data/countries_1936.csv` (P06). Capitals: the state holding each country's 1936 capital VP.
- Game files at `$HOI4_GAME_DIR` (read-only).

## 4. CONSTRAINTS
- Hard: every country owning ≥ 1 state has `history/countries/<TAG> - <Name>.txt` with a valid `capital = <state id>` that it owns.
- Hard: no vanilla file that references a state/province id may remain active unless the id means the same place (it won't) — neutralise via `replace_path` or same-name empty override; list every neutralised file.
- Hard: minimal OOBs — either none (`history/units` replaced with empty per-country files referenced by country history) or generated garrisons placed on valid provinces.
- Hard: localisation UTF-8 BOM; every key used by map/state/region/adjacency/continent files exists.
- Preference: keep vanilla ideologies, technologies, equipment, characters (they don't reference map ids) — verify by scan.
- Discretion: stub mechanism per folder.

## 5. DECISION RULES
- For each vanilla folder: scan with `tools/scan_vanilla_refs.py` (patterns in 10-mod-integration §4). Folder with hits → `replace_path` (if the whole folder is content we will rewrite later: national_focus, events, decisions, ai_strategy, scripted_effects/triggers with map ids, bookmarks) or same-name overrides for the hit files only (if few). Record the choice per folder.
- If a folder is required to exist non-empty by the engine (e.g. bookmarks, ideas) → provide a minimal valid file.
- If unsure whether a file references map ids → treat it as referencing (safe side) and list it.

## 6. FAILURE MODES
1. Missing `replace_path="history/states"` → vanilla states load on top → crash.
2. A bookmark referencing vanilla country setups that no longer exist.
3. Tag referenced in states but missing in `common/country_tags`.

## 7. EXECUTION WORKFLOW
INSPECT → SCAN (report of hits per folder) → PLAN (neutralisation table in log) → EXECUTE → VERIFY → REPORT.

## 8. VERIFICATION COMMANDS
- `python3 .claude/skills/hoi4-map-modding/scripts/validate_map.py mod --vanilla "$HOI4_GAME_DIR" --json build/validate_p11.json` → 0 ERROR.
- `python3 tools/scan_vanilla_refs.py --effective mod "$HOI4_GAME_DIR"` → 0 active files with map-id references outside `mod/history/states` and `mod/map`.
- Localisation key check script → 0 missing keys; BOM present on all yml.

## 9. STOP CONDITION & CHECKPOINT
Commit `mod(p11): packaging and vanilla neutralisation`. HARD STOP at Gate G5 — final message: the exact steps for the owner's in-game test (P12).
