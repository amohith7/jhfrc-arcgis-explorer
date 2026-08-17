# JHFRC ArcGIS Explorer

Cross-county comparison layer for the JHFRC Community Profiles rollout.
Reads per-county outputs from the sibling `jhfrc-community-profiles`
project, builds a unified tract-level dataset, joins it to TIGER/Line
tract polygons, and publishes to ArcGIS Online as a Hosted Feature
Layer that powers an **ArcGIS Dashboards** app for interactive
cross-county exploration.

> **Owner:** Mohith Pavan Addepalli
> **Organization:** Journey Health Foundation Research Center (JHFRC),
> University of Tennessee at Chattanooga
> **Sibling project (read-only source):** `../jhfrc-community-profiles/output/`

## Why this exists

The Community Profiles PDF is county-scoped by design — one PDF per
county. Once the rollout crosses ~10 counties, comparing them means
opening a stack of 47 PDFs. That's not workable.

This project produces:

1. A **unified tract-level dataset** (`rollout_indicators.parquet` +
   `.csv` + `.sqlite`) — every county's indicators in one tidy file,
   filterable and joinable in any BI tool.
2. A **map-ready Shapefile** (`jhfrc_tracts.shp` /
   `jhfrc_tracts.gpkg`) joining that dataset to TIGER/Line tract
   polygons.
3. A **published Hosted Feature Layer** on ArcGIS Online, which
   powers an **ArcGIS Dashboards** app for interactive cross-county
   exploration: pick indicator → get ranked bar chart + choropleth
   + delta gauges.

The reports pipeline is untouched — this project reads its `output/`
folder as source-of-truth.

## Why ArcGIS Dashboards

Dashboards is the right fit for the specific "compare counties on
any indicator" workflow:

- Purpose-built for KPI/ranking style comparison across geographies.
- Constrained widget set (indicator selector, ranked list, choropleth,
  gauges, tables) = fast to build, low maintenance.
- Included in every ArcGIS Online subscription (no add-on license).
- Works on mobile out of the box.
- Same underlying Feature Layer can later feed Experience Builder,
  Instant Apps, or Insights without any Python-side changes.

If you have an **Insights** license and want more exploratory
analytics (correlation, cross-filtering), you can point Insights at
the same Feature Layer without changing anything in this project.

## Prerequisites

- Python 3.9+
- `pip install -r requirements.txt`
- Read access to `../jhfrc-community-profiles/output/`
- ArcGIS Online account with permission to create Hosted Feature Layers
  (only required for `publish_to_arcgis.py`)

## Workflow

```bash
# 1. Aggregate every built county's XML into one tidy dataset
python build_rollout_dataset.py

# 2. Join to TIGER polygons and emit a Shapefile / GeoPackage
python build_arcgis_layer.py

# 3. Publish (or overwrite) the Hosted Feature Layer on ArcGIS Online
python publish_to_arcgis.py

# 4. In the ArcGIS Online browser: build a Dashboard on top of the layer
#    (see docs/dashboard_build.md for the widget list + config)
```

Each script is independent — you can run 1 → 2 → 3 in one sitting, or
run just #1 to refresh the flat dataset without republishing the
Feature Layer. See `docs/workflow.md` for details on inputs, outputs,
and configuration.

## Auth

Never hardcode ArcGIS credentials in a script or a config file. Two
supported patterns:

- `ARCGIS_USERNAME` + `ARCGIS_PASSWORD` env vars, or
- Interactive OAuth on first run (opens your browser to sign in;
  session cached under `~/.arcgis/`).

Detected automatically by `publish_to_arcgis.py`.

## Layout

```
jhfrc-arcgis-explorer/
├── README.md                      This file
├── requirements.txt               Python deps (arcgis, geopandas, ...)
├── .gitignore
├── build_rollout_dataset.py       Scans reports output/, emits Tier 1 dataset
├── build_arcgis_layer.py          Joins dataset to TIGER polygons -> Shapefile
├── publish_to_arcgis.py           Uploads Feature Layer to ArcGIS Online
├── docs/
│   ├── workflow.md                Step-by-step guide with expected outputs
│   └── dashboard_build.md         Widget list + config for the Dashboard app
├── scripts/                       One-off helpers, not part of the main flow
└── data/                          Generated artifacts (gitignored)
```
