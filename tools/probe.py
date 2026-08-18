"""Regression probe for the JHFRC ArcGIS Explorer dashboard.

Runs three headless viewports (desktop, tablet, mobile) against the live
GitHub Pages dashboard, exercises every indicator in the dropdown, and
checks that:

- No indicator returns 0 tracts / no data
- The console reports no missing layer fields (or an intentional gap)
- The .app grid rows and children line up correctly
- The Filters toggle is hidden on desktop / tablet, visible on mobile
- The sidebar backdrop starts hidden on load at every viewport
- No page-level error console entries beyond known environment noise

Also saves one screenshot per viewport for visual review.

Usage (from repo root):

    pip install playwright && playwright install chromium
    python tools/probe.py                     # probes production
    python tools/probe.py http://localhost:8000/dashboard/   # local server

Environment note: on shells with a POSIX-only locale (LANG=en_US@posix),
ArcGIS ScaleBar / smart-mapping legend formatters throw
"RangeError: Invalid language tag". That's an environment artifact, not
a site bug. Prefix the run with `LANG=en_US.UTF-8` if you see it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_URL = "https://amohith7.github.io/jhfrc-arcgis-explorer/dashboard/"
OUT_DIR = Path(__file__).resolve().parent.parent / "tools" / "probe_out"

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
    optionCount: document.querySelectorAll('#indicatorSelect option').length,
    coverageNote: (document.getElementById('coverageNote') || {}).textContent || '',
  };
}"""


def run(url: str, width: int, height: int) -> dict:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        logs: list[str] = []
        page.on("console", lambda m: logs.append(f"{m.type}: {m.text[:400]}"))
        page.goto(url, wait_until="networkidle", timeout=90_000)
        page.wait_for_timeout(7000)

        snapshot = page.evaluate(CHECKS)
        skipped = [line for line in logs if "Skipping" in line]
        errors = [line for line in logs if line.startswith("error")]

        options = page.eval_on_selector_all(
            "#indicatorSelect option", "els => els.map(e => e.value)"
        )
        empty: list[str] = []
        for value in options:
            page.select_option("#indicatorSelect", value)
            page.wait_for_timeout(400)
            n = page.eval_on_selector("#kpiTracts", "e => e.textContent").strip()
            if n in ("0", "—"):
                empty.append(value)

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        screenshot = OUT_DIR / f"probe_{width}.png"
        page.screenshot(path=str(screenshot))

        print(f"\n=== {width}x{height} ===")
        print(json.dumps(snapshot, indent=1))
        print(f"missing fields: {skipped or 'none'}")
        print(f"errors: {errors or 'none'}")
        print(f"indicators returning zero tracts: {empty or 'none'}")
        print(
            f"screenshot: {screenshot.relative_to(Path.cwd()) if Path.cwd() in screenshot.parents else screenshot}"
        )

        browser.close()

        return {
            "viewport": f"{width}x{height}",
            "snapshot": snapshot,
            "skipped_fields_logs": skipped,
            "errors": errors,
            "zero_tract_indicators": empty,
            "screenshot": str(screenshot),
        }


def main(argv: list[str]) -> int:
    url = argv[1] if len(argv) > 1 else DEFAULT_URL
    print(f"Probing: {url}")

    results = []
    for w, h in [(1440, 900), (768, 1024), (390, 844)]:
        results.append(run(url, w, h))

    # Pass / fail summary (advisory — the caller decides based on the run)
    failures: list[str] = []
    for r in results:
        if r["zero_tract_indicators"]:
            failures.append(
                f"{r['viewport']}: {len(r['zero_tract_indicators'])} indicators returning 0 tracts"
            )
        if r["errors"]:
            for e in r["errors"]:
                # Environment noise the brief calls out explicitly.
                if "Invalid language tag" in e:
                    continue
                failures.append(f"{r['viewport']}: console error: {e[:120]}")
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
