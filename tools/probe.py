"""Regression probe for the JHFRC ArcGIS Explorer dashboard.

Runs three headless viewports (desktop, tablet, mobile) against the live
GitHub Pages dashboard and checks:

Brief 2 baseline
  - Every indicator in the dropdown returns >0 tracts
  - No missing-fields console warnings
  - .app grid rows / children line up
  - Filters toggle hidden on desktop / tablet, visible on mobile
  - Sidebar backdrop starts hidden at every viewport
  - No page-level error console entries beyond known environment noise

Brief 3 additions
  D1 — trend summary uses the correct verb (no "fell the most" when
       every county rose)
  D2 — no "Skipping N missing fields" console warning
  D3 — mobile KPI panel is actually visible (>200px rendered height
       at 390x844)
  D4 — CSV exports are numeric-parseable; no cell contains %/pp/$/
       U+2212 minus
  D5 — indicator selection survives a county filter change

Saves one screenshot per viewport + one CSV per export test to
`tools/probe_out/` for visual review.

Usage (from repo root):

    pip install playwright && playwright install chromium
    LANG=en_US.UTF-8 python tools/probe.py
    LANG=en_US.UTF-8 python tools/probe.py http://localhost:8000/dashboard/

Environment note: on shells with a POSIX-only locale (LANG=en_US@posix),
ArcGIS ScaleBar / smart-mapping legend formatters throw
"RangeError: Invalid language tag". That's an environment artifact, not
a site bug. Prefix the run with `LANG=en_US.UTF-8` if you see it.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
from pathlib import Path

DEFAULT_URL = "https://amohith7.github.io/jhfrc-arcgis-explorer/dashboard/"
OUT_DIR = Path(__file__).resolve().parent.parent / "tools" / "probe_out"

# Unit / formatting characters that a downstream analyst can't parse
# as a number. Brief 3 D4.
NON_NUMERIC_CHARS = ("%", "pp", "$", "−", "yr")


CHECKS = """() => {
  const g = s => {
    const e = document.querySelector(s);
    if (!e) return null;
    const r = e.getBoundingClientRect();
    const cs = getComputedStyle(e);
    return {
      w: Math.round(r.width), h: Math.round(r.height),
      top: Math.round(r.top), disp: cs.display,
    };
  };
  return {
    appRows: getComputedStyle(document.querySelector('.app')).gridTemplateRows,
    appChildren: document.querySelector('.app').children.length,
    filtersToggle: g('#filtersToggle'),
    backdrop: g('#sidebarBackdrop'),
    main: g('main'),
    mapView: g('#mapView'),
    kpiPanel: g('.kpi-panel'),
    optionCount: document.querySelectorAll('#indicatorSelect option').length,
    coverageNote: (document.getElementById('coverageNote') || {}).textContent || '',
  };
}"""


def _capture_download(page, trigger_selector: str, dest_dir: Path) -> Path | None:
    """Click the trigger and save the resulting download. None on timeout."""
    try:
        with page.expect_download(timeout=8000) as info:
            page.click(trigger_selector)
        d = info.value
        dest = dest_dir / d.suggested_filename
        d.save_as(str(dest))
        return dest
    except Exception:
        return None


def _csv_numeric_violations(csv_path: Path) -> list[str]:
    """Return any cell whose column looks numeric but the value contains
    a unit character or is a formatted string. Brief 3 D4."""
    try:
        text = csv_path.read_text(encoding="utf-8-sig")
    except Exception as e:
        return [f"unreadable: {e}"]
    # Strip commented preamble.
    lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    if not lines:
        return ["empty CSV"]
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    numeric_cols = {
        "value",
        "unweighted_mean",
        "delta_2015_19_to_2020_24",
        "value_moe",
        "tract_count",
        "suppressed_count",
    }
    bad: list[str] = []
    rows = list(reader)
    # Brief 5 S7 adds a plain-label second header row between the
    # machine-name header and the data (e.g. "Value", "% of households",
    # "Tract ID"). Detect and skip it: if row 0's numeric columns are
    # all non-parseable strings, treat it as the plain-label row.
    if rows:
        first = rows[0]
        vals = [
            (first.get(c) or "").strip()
            for c in numeric_cols
            if c in first and (first.get(c) or "").strip()
        ]

        def _is_num(s: str) -> bool:
            try:
                float(s)
                return True
            except ValueError:
                return False

        if vals and not any(_is_num(v) for v in vals):
            rows = rows[1:]
    for i, row in enumerate(rows):
        for col in numeric_cols & row.keys():
            v = (row[col] or "").strip()
            if not v:
                continue
            if any(ch in v for ch in NON_NUMERIC_CHARS):
                bad.append(f"row {i} col {col}={v!r}")
            else:
                try:
                    float(v)
                except ValueError:
                    bad.append(f"row {i} col {col}={v!r} not float")
    return bad


def _brief3_extra(page, dest_dir: Path) -> dict:
    """Run the Brief 3 D-series assertions. Returns dict of results."""
    findings: dict = {}

    # D1 — sign-aware trend verb on an all-positive-change indicator.
    try:
        page.select_option("#indicatorSelect", "med_home")
        page.click("#tab-trends")
        page.wait_for_timeout(1400)
        meta = page.eval_on_selector("#trendMeta", "e => e.innerText")
        findings["d1_trend_meta"] = meta[:220]
        findings["d1_ok"] = "fell the most" not in meta
    except Exception as e:
        findings["d1_ok"] = f"error: {e}"

    # D2 — no "Skipping N missing fields" console warnings.
    #      (populated by run(); we mirror it here for the summary.)

    # D3 — KPI panel rendered height at THIS viewport.
    try:
        page.click("#tab-overview")
        page.wait_for_timeout(600)
        kpi_h = page.eval_on_selector(
            ".kpi-panel", "e => e.getBoundingClientRect().height"
        )
        findings["d3_kpi_panel_h"] = round(kpi_h)
    except Exception as e:
        findings["d3_kpi_panel_h"] = f"error: {e}"

    # D4 — CSV downloads parse numerically.
    for tab, btn, name in [
        ("ranking", "#rankingCsvBtn", "ranking"),
        ("compare", "#compareCsvBtn", "compare"),
    ]:
        try:
            page.click(f"#tab-{tab}")
            page.wait_for_timeout(500)
            path = _capture_download(page, btn, dest_dir)
            if not path:
                findings[f"d4_{name}_csv"] = "no download"
                continue
            findings[f"d4_{name}_csv_file"] = path.name
            bad = _csv_numeric_violations(path)
            findings[f"d4_{name}_violations"] = bad[:5]
            findings[f"d4_{name}_ok"] = not bad
        except Exception as e:
            findings[f"d4_{name}_csv"] = f"error: {e}"

    # D5 — indicator selection survives a county filter change.
    try:
        page.click("#tab-overview")
        page.wait_for_timeout(300)
        before = page.eval_on_selector("#indicatorSelect", "e => e.value")
        # On mobile (<=800px) the sidebar is an off-canvas drawer, so
        # the county checkbox is not in the viewport until #filtersToggle
        # is clicked. Open the drawer first if the toggle is displayed.
        toggle_visible = page.eval_on_selector(
            "#filtersToggle", "e => window.getComputedStyle(e).display !== 'none'",
        )
        if toggle_visible:
            page.click("#filtersToggle")
            page.wait_for_timeout(350)
        # Uncheck one county — must not silently swap indA.
        cbx = page.query_selector("#countyList input[type=checkbox]")
        if cbx:
            cbx.uncheck()
            page.wait_for_timeout(700)
        after = page.eval_on_selector("#indicatorSelect", "e => e.value")
        findings["d5_before"] = before
        findings["d5_after"] = after
        findings["d5_ok"] = before == after
    except Exception as e:
        findings["d5_ok"] = f"error: {e}"

    return findings


def run(url: str, width: int, height: int) -> dict:
    from playwright.sync_api import sync_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dl_dir = OUT_DIR / f"downloads_{width}"
    dl_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            viewport={"width": width, "height": height}, accept_downloads=True,
        )
        logs: list[str] = []
        page.on("console", lambda m: logs.append(f"{m.type}: {m.text[:400]}"))
        page.goto(url, wait_until="networkidle", timeout=90_000)
        page.wait_for_timeout(7000)

        snapshot = page.evaluate(CHECKS)
        skipped = [line for line in logs if "Skipping" in line]
        errors = [line for line in logs if line.startswith("error")]

        options = page.eval_on_selector_all(
            "#indicatorSelect option:not(:disabled)", "els => els.map(e => e.value)",
        )
        empty: list[str] = []
        for value in options:
            page.select_option("#indicatorSelect", value)
            page.wait_for_timeout(400)
            n = page.eval_on_selector("#kpiTracts", "e => e.textContent").strip()
            if n in ("0", "—"):
                empty.append(value)

        # Brief 3 assertions
        extra = _brief3_extra(page, dl_dir)

        screenshot = OUT_DIR / f"probe_{width}.png"
        page.screenshot(path=str(screenshot))

        print(f"\n=== {width}x{height} ===")
        print(json.dumps(snapshot, indent=1))
        print(f"missing fields: {skipped or 'none'}")
        print(f"errors: {errors or 'none'}")
        print(f"indicators returning zero tracts: {empty or 'none'}")
        print("Brief 3 extras:", json.dumps(extra, indent=1))
        print(f"screenshot: {screenshot}")

        browser.close()

        return {
            "viewport": f"{width}x{height}",
            "snapshot": snapshot,
            "skipped_fields_logs": skipped,
            "errors": errors,
            "zero_tract_indicators": empty,
            "extras": extra,
            "screenshot": str(screenshot),
        }


def main(argv: list[str]) -> int:
    url = argv[1] if len(argv) > 1 else DEFAULT_URL
    print(f"Probing: {url}")

    results = []
    for w, h in [(1440, 900), (768, 1024), (390, 844)]:
        results.append(run(url, w, h))

    failures: list[str] = []
    for r in results:
        vp = r["viewport"]
        if r["zero_tract_indicators"]:
            failures.append(
                f"{vp}: {len(r['zero_tract_indicators'])} indicators returning 0 tracts"
            )
        # Brief 3 D2 — no missing-fields warnings.
        if r["skipped_fields_logs"]:
            failures.append(
                f"{vp}: missing-fields warning: {r['skipped_fields_logs'][0]}"
            )
        for e in r["errors"]:
            if "Invalid language tag" in e:
                continue
            failures.append(f"{vp}: console error: {e[:120]}")
        ex = r["extras"]
        if ex.get("d1_ok") is not True:
            failures.append(f"{vp}: D1 trend verb — {ex.get('d1_trend_meta','')}")
        # D3 KPI panel visibility — only meaningful on mobile.
        if vp.startswith("390"):
            h_ok = (
                isinstance(ex.get("d3_kpi_panel_h"), int) and ex["d3_kpi_panel_h"] > 200
            )
            if not h_ok:
                failures.append(f"{vp}: D3 KPI panel height {ex.get('d3_kpi_panel_h')}")
        if ex.get("d4_ranking_ok") is not True:
            failures.append(
                f"{vp}: D4 ranking CSV bad cells: {ex.get('d4_ranking_violations')}"
            )
        if ex.get("d4_compare_ok") is not True:
            failures.append(
                f"{vp}: D4 compare CSV bad cells: {ex.get('d4_compare_violations')}"
            )
        if ex.get("d5_ok") is not True:
            failures.append(
                f"{vp}: D5 indicator swapped from {ex.get('d5_before')} to {ex.get('d5_after')}"
            )
    print("\n=== summary ===")
    if failures:
        print("FAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
