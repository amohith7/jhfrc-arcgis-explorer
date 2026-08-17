# Workflow

Three commands, each independent. Run in order for a full refresh, or
in isolation to iterate on one stage.

## 0. One-time setup

```bash
cd ~/Downloads/Claude/jhfrc-arcgis-explorer
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Confirm the sibling reports project is present:

```bash
ls ../jhfrc-community-profiles/output/
```

Every subfolder there like `TN_Sequatchie/` becomes a source county.

## 1. Aggregate — `build_rollout_dataset.py`

```bash
python build_rollout_dataset.py
```

**What it does:** walks `../jhfrc-community-profiles/output/*/`, parses every county's Community Profiles XML, emits one tidy dataset in three format variants.

**Outputs:**

- `data/rollout_indicators.parquet` — analytics-friendly (pandas, DuckDB, R, Tableau)
- `data/rollout_indicators.csv` — universal (Excel, Google Sheets, Notion)
- `data/rollout_indicators.sqlite` — ad-hoc SQL (`sqlite3 data/rollout_indicators.sqlite`)

**Row grain:** one row per `(state, county, tract, indicator, vintage)`. About 90 indicators per tract × 1,913 tracts × 1 current vintage ≈ 170K rows for the full 47-county rollout.

**Idempotent:** rerun after every new county build. Overwrites the output files.

## 2. Join to polygons — `build_arcgis_layer.py`

```bash
python build_arcgis_layer.py
```

**What it does:**

1. Loads `data/rollout_indicators.parquet`.
2. Filters to the ~40 headline indicators (edit `HEADLINE_INDICATORS` in the script to change the set).
3. Pivots wide (one row per tract, one column per indicator + `_d5` delta + `_supp` suppression flag).
4. Joins to TIGER/Line tract polygons from `../jhfrc-community-profiles/data/census_tracts.gpkg`.
5. Emits three format variants.

**Outputs:**

- `data/jhfrc_tracts.gpkg` — GeoPackage, preferred upload format for AGOL
- `data/jhfrc_tracts.shp` (+ .shx .dbf .prj .cpg) — Shapefile, 10-char field name limit
- `data/jhfrc_tracts.geojson` — for quick QA in a browser (e.g., geojson.io)

**Attribute schema per tract:**

| Field | Type | Example |
|---|---|---|
| tract_geoid | string(11) | `47153060102` |
| state_abbr | string(2) | `TN` |
| county_fips | string(5) | `47153` |
| county_name | string | `Sequatchie` |
| `pov_below` (and 39 other short_ids) | float | `18.4` |
| `pov_below_d5` (and 39 other _d5) | float | `-1.2` |
| `pov_below_supp` (and 39 other _supp) | bool | `false` |
| geometry | Polygon | (TIGER 2020) |

## 3. Publish — `publish_to_arcgis.py`

```bash
python publish_to_arcgis.py
```

**What it does:** uploads `data/jhfrc_tracts.gpkg` to ArcGIS Online. First run creates a Hosted Feature Layer titled "JHFRC Tracts". Subsequent runs OVERWRITE that same layer in place — the item id, URL, sharing settings, and any Dashboards that reference it all survive.

**Auth (auto-detected):** environment variables (`ARCGIS_USERNAME` + `ARCGIS_PASSWORD`, or `ARCGIS_TOKEN`), or interactive OAuth on first run. See `README.md` for details.

**Sharing:** set to PRIVATE by default. Open the item in AGOL, click Share, and pick group / org / public as appropriate. If you make it public, share BOTH the Feature Layer AND any Dashboard that references it — otherwise anonymous viewers see an empty map.

## 4. Build the Dashboard

See `docs/dashboard_build.md` for the widget list + configuration steps in the AGOL browser UI (no code).

## Refresh cadence

The dataset changes any time a county finishes its pipeline run. A typical refresh is:

```bash
# After the reports project finishes building N counties
cd ~/Downloads/Claude/jhfrc-arcgis-explorer
source .venv/bin/activate
python build_rollout_dataset.py && python build_arcgis_layer.py && python publish_to_arcgis.py
```

The three steps take about 30 seconds combined for a 47-county rollout. The Dashboard picks up the new data automatically — no republishing the app.

## Troubleshooting

- **"No county XML files found"** — check `ls ../jhfrc-community-profiles/output/`. Each folder must contain `<County>_County_Community_Profiles.xml`. The reports pipeline emits this in Phase 3.
- **"TIGER tract polygons missing"** — the reports project ships `data/census_tracts.gpkg` (47-county subset). If it's missing, pull the latest of that repo.
- **Field name too long in Shapefile** — Shapefile caps field names at 10 chars. `HEADLINE_INDICATORS` short_ids are already ≤ 10; edit them in `build_arcgis_layer.py` if you add new ones.
- **Overwrite fails with "schema mismatch"** — AGOL requires the overwrite payload to match the original schema exactly. If you add / remove indicators, delete the item in AGOL and re-run with `--no-overwrite` to force a fresh publish (this WILL invalidate existing Dashboards).
