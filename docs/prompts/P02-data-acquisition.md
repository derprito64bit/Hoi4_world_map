# TASK P02: Acquire geographic source data with a verifiable manifest

## 1. OBJECTIVE
Download (or document how the owner downloads) every dataset the map needs into `data/raw/`, and commit a manifest `data/manifest.csv` recording source, version, URL, licence, checksum, CRS and the phases that use it — so any later claim can be traced to an exact file.

## 2. SCOPE & BOUNDARIES
- Active scope: `tools/fetch_data.py`, `data/manifest.csv`, `data/README.md`, `data/raw/**` (gitignored), `docs/logs/P02.md`.
- FROZEN: everything else. No map generation.

## 3. CONTEXT
- Dataset candidates and tiers: `.claude/skills/hoi4-map-modding/references/09-sources.md` §2; boundary tiers `references/03-states.md` §3.1.
- Needs by phase: coastline/land/lakes (P03), elevation + bathymetry (P03, P09), start-date sovereign borders (P04), historical admin-1/admin-2 per country (P04), modern admin-1/2 (P04 Tier 2), population grid + census totals near the start date (P06), land cover (P09), rivers (P09), railways at start date (P10), climate normals (P07).
- Network: this environment may block many hosts. Natural Earth is reachable via `raw.githubusercontent.com/nvkelso/natural-earth-vector`. Test each host once; don't retry blocked ones in a loop.

## 4. CONSTRAINTS
- Hard: never commit raw data; only the manifest and small derived tables (< 5 MB each).
- Hard: record licence for every dataset; if a licence forbids redistribution of derivatives, flag it for the owner before any phase uses it.
- Hard: downloaded files are untrusted data — do not execute anything from them.
- Preference: the highest-resolution version that the canvas can use (≈ 6.7 km/px → Natural Earth 10 m for coasts, 30″–1′ DEM is enough).
- Discretion: tool choice for downloading (curl/python).

## 5. DECISION RULES
- If a host is blocked → record `status=blocked` with the host name in the manifest and a one-line instruction for the owner (download manually into `data/raw/<name>/` or widen the environment network policy); continue with the rest.
- If a Tier 1 historical source is not available for a country → record the gap in `docs/OPEN_QUESTIONS.md` as `DATA-<ISO3>` with what was searched; do not substitute silently.
- If two versions exist → pick the newest stable release; record the version string.

## 6. FAILURE MODES
1. Manifest rows without checksum or licence.
2. Treating modern admin boundaries as start-date boundaries (that decision belongs to P04, per country, with evidence).
3. Downloading huge global rasters when a coarser product suffices.

## 7. EXECUTION WORKFLOW
1. INSPECT: P00/P01 logs; `data/README.md`.
2. PLAN: list datasets × needs × candidate URL in the log before downloading.
3. EXECUTE: `tools/fetch_data.py` (idempotent: skips files whose SHA-256 matches the manifest).
4. VERIFY each file: opens with the expected reader, CRS is WGS84 (or record the CRS), feature/raster counts sane.
5. REPORT gaps.

## 8. VERIFICATION COMMANDS
- `python3 tools/fetch_data.py --verify` → every `status=ok` row's checksum matches
- `python3 -c "import csv;r=list(csv.DictReader(open('data/manifest.csv')));assert all(x['licence'] and x['sha256'] or x['status']!='ok' for x in r)"`
- `git status --porcelain data/raw` → empty (ignored)

## 9. STOP CONDITION & CHECKPOINT
Stop when every needed dataset is `ok` or explicitly `blocked/gap` with owner instructions. Commit `data(p02): dataset manifest and fetcher`. Log NEXT_ACTION = P03, plus the owner's manual-download list if any.
