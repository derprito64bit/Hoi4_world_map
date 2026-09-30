# data/

- `manifest.csv` — one row per downloaded dataset: id, version, source URL, local path, SHA-256, licence, CRS, phases using it, retrieval date. Committed.
- `raw/` — downloaded source files. **Gitignored**; never commit raw data. Re-create with the tool named in the manifest row; tools verify the pinned SHA-256 and refuse a mismatch.
- `countries/` — country/status calibration data.

## Current datasets
| id | used by | note |
|---|---|---|
| `ne_50m_land` | P00d (`python tools/projection/hybrid.py preview`) | Natural Earth 1:50m land 4.1.0, public domain. **Preview-only**: land shapes for the hybrid-projection previews and seam statistics (`build/projection/`). Downloaded automatically to `data/raw/naturalearth/ne_50m_land.zip`. Not a geometry source for the map; P02 does the full data acquisition. |
