# Hosting the custom dashboard on GitHub Pages

The `dashboard/index.html` is a single-file web app that reads directly from the JHFRC Tracts Hosted Feature Layer on ArcGIS Online. No backend needed — it runs entirely in the browser. GitHub Pages hosts it for free at a public URL.

## One-time setup (2 minutes)

1. Open the repo on GitHub:
   [https://github.com/amohith7/jhfrc-arcgis-explorer](https://github.com/amohith7/jhfrc-arcgis-explorer)
2. Click **Settings** (top nav) → **Pages** (left sidebar).
3. Under "Build and deployment", set:
   - **Source:** Deploy from a branch
   - **Branch:** `main` — folder: `/ (root)` — click **Save**.
4. Wait 30-90 seconds while GitHub builds. Refresh the Pages settings page — you'll see a green box with the URL:
   ```
   https://amohith7.github.io/jhfrc-arcgis-explorer/
   ```
5. The dashboard is at:
   ```
   https://amohith7.github.io/jhfrc-arcgis-explorer/dashboard/
   ```
   Open that URL in any browser. Share it with anyone.

That's it — no server, no build step, no auth. The Feature Layer is public, so anyone with the dashboard URL can view.

## What the dashboard does

Five tabs across the top:

- **Overview** — choropleth map + KPI tiles (average, median, min, max, std dev, range) + county-average bar chart + top 10 tracts
- **Correlation** — scatter plot of any two indicators + Pearson r + a 10-indicator correlation matrix
- **Compare Counties** — pick two counties, see all 40 indicators side by side with the winner marked
- **Trends (5-yr)** — 5-year change by county + tract-level distribution histogram
- **Tract Ranking** — full ranked list of all visible tracts, worst/best 10% color-coded

Left sidebar controls:
- **Primary Indicator** — drives the map, KPIs, ranking, trends
- **Secondary Indicator** — drives the correlation scatter
- **Counties** — multi-select filter, applies to every view

## Updates after a data refresh

The dashboard reads live from the ArcGIS Feature Layer. Any refresh of the layer (via `publish_to_arcgis.py` or manual re-upload) shows in the dashboard **immediately on next page load** — no rebuild of this project needed.

If you change the dashboard HTML itself (add a chart, change styling, etc.):

```bash
cd ~/Downloads/Claude/jhfrc-arcgis-explorer
git add dashboard/
git commit -m "Update dashboard UI"
git push
```

GitHub Pages redeploys automatically within ~1-2 minutes.

## Local development

To open the file directly without deploying:

```bash
open ~/Downloads/Claude/jhfrc-arcgis-explorer/dashboard/index.html
```

macOS opens it in your default browser as `file:///Users/…/dashboard/index.html`. All widgets work locally because the Feature Layer is fetched over the network the same way. Use this for iteration; commit + push when you're happy with the result to update the public URL.

## Security notes

- The Feature Layer's REST endpoint is public read. The dashboard has no write path.
- No user credentials are read or transmitted. No cookies. No third-party trackers.
- Everything is fetched from three CDNs: ArcGIS JS SDK (js.arcgis.com), Chart.js (jsdelivr.net), and the annotation plugin (jsdelivr.net). If a viewer's network blocks those, the dashboard won't load — same failure mode as any web app.
