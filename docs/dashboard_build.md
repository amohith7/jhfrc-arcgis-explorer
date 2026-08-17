# Building the ArcGIS Dashboard

No code — everything is done in the ArcGIS Online browser UI. Takes about 30-45 minutes for the first build.

## Prerequisites

- The Feature Layer "JHFRC Tracts" is published (see `workflow.md`).
- Your AGOL account has "Publisher" or higher role.

## Recommended layout

A three-column layout with a header:

```
┌──────────────────────────────────────────────────────────────────┐
│  Header:  JHFRC Community Profiles – Regional Explorer          │
├────────────┬──────────────────────────────────┬─────────────────┤
│            │                                  │                 │
│  Filters   │            Choropleth Map        │  Ranked List    │
│            │                                  │  (indicator)    │
│  • State   │                                  │                 │
│  • Domain  │                                  │  1. Tract A     │
│  • Indic.  │                                  │  2. Tract B     │
│            │                                  │  ...            │
│            ├──────────────────────────────────┼─────────────────┤
│            │      Delta Bar Chart (5-yr)      │  Gauges         │
│            │                                  │  (State/County/ │
│            │                                  │   US benchmarks)│
└────────────┴──────────────────────────────────┴─────────────────┘
```

## Widget-by-widget

### 1. Header

- Type: Header
- Title: "JHFRC Community Profiles — Regional Explorer"
- Subtitle: "Cross-county SDoH indicators, TN / GA / AL / NC"

### 2. Filters (left sidebar)

Three Category Selector widgets stacked, each pointing at the JHFRC Tracts layer:

- **State** — field `state_abbr`
- **County** — field `county_name`
- **Indicator** — this one is a bit different. Since indicators are stored as columns, not values, use a Category Selector wired to a small helper table, or use a URL parameter selector. Simplest: List Selector with the ~40 headline indicator short_ids hardcoded.

### 3. Choropleth Map (center)

- Type: Map
- Source: JHFRC Tracts feature layer
- Style: choropleth, tied to the currently selected indicator's field via a data expression
- Popup: shows all headline indicators for the clicked tract, plus a 5-year delta arrow (`_d5` fields)
- Basemap: "Light Gray Canvas" (keeps focus on the choropleth)

### 4. Ranked List (right column, top)

- Type: List
- Source: JHFRC Tracts
- Sort by the selected indicator descending
- Item template: `<b>{tract_geoid}</b> — {county_name}<br>{indicator_value}`
- Limit: top 25

### 5. Delta Bar Chart (center bottom)

- Type: Serial Chart
- Category field: `county_name`
- Value field: mean of the selected indicator's `_d5` column, grouped by county
- Sort ascending so counties trending worst are visible on the left
- Color rule: negative = green, positive = red for "bad-is-up" indicators (opposite for "good-is-up")

### 6. Benchmark Gauges (right column, bottom)

- Three Gauge widgets in a row: County Avg, State Avg, US Avg
- Data expression: mean of the selected indicator across the filter selection
- Show delta vs. the selected tract when a single tract is picked

## Interaction rules

- **State filter** → filters Map + List + Chart + Gauges to that state's tracts
- **County filter** → further narrows all of the above
- **Indicator filter** → changes the field the Map, List, and Chart pull from
- **Click a tract on the Map** → syncs a highlight on the List and Gauges

## Sharing

Once the Dashboard renders correctly:

1. Save the Dashboard item.
2. Click Share → pick Everyone (public), your JHFRC org, or a specific group.
3. **Also share the underlying Feature Layer** with the same audience. Otherwise the map is blank for anyone who doesn't own the layer.
4. Copy the Dashboard URL and send to Tracy + Kim.

## Optional: wrap in an ArcGIS Hub site

If you want a branded landing page that hosts the Dashboard + a download button for the CSV + a StoryMap with methodology, create an ArcGIS Hub site and embed the Dashboard as a card.

## Iteration

The Dashboard reads live from the Feature Layer. Any pipeline refresh (new counties, indicator changes) just needs `publish_to_arcgis.py` to overwrite the layer — the Dashboard picks up the new numbers automatically, no re-publishing the app.
