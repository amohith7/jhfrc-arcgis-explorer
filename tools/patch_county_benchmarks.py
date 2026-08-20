"""One-off fast-path fix for the community-profiles CountyValue
replication bug (2026-08-20). Rewrites <CountyValue> in each pilot
county XML with the correct per-county mean computed directly from
the vendor 2024 data.xlsx (ACS) and CDC PLACES county-level API
(PLACES).

Background: the community-profiles pipeline had two cache filenames
that omitted COUNTY_FIPS, so after the first county was generated
(Hamilton), every subsequent county read Hamilton's cached
benchmarks. Compounded by a fuzzy-match fallback against a tiny
6-item age-only SDOH file, this produced values like
"Median Household Income ($)" = "$24" across all 11 counties
(actually the mean of a 'Median Income (Grandparents)' column that
happened to token-match).

This script skips the broken pipeline path entirely. For every
Indicator in every county XML, it:

  1. Looks up the county mean directly from vendor 2024 data.xlsx
     (ACS indicators) using label match.
  2. Pulls county mean from CDC PLACES county API (PLACES
     indicators) — cached per-county to
     data/places_county_cache.json.
  3. Updates just the <CountyValue> element. StateValue and
     USValue are left as-is (they can legitimately be identical
     across counties). Follow-up will address those separately.

Idempotent: re-runs re-fetch nothing (uses local + cached data).

Usage (from repo root):
    python tools/patch_county_benchmarks.py
    python tools/patch_county_benchmarks.py --dry-run

Downstream: after this runs, rebuild the rollout + GPKG:
    python build_rollout_dataset.py
    python build_arcgis_layer.py --formats gpkg
    python publish_to_arcgis.py --title "JHFRC Tracts v11" --no-overwrite
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
COMMUNITY = REPO.parent / "jhfrc-community-profiles"
VENDOR_XLSX = COMMUNITY / "data" / "2024 data.xlsx"
OUTPUT_ROOT = COMMUNITY / "output"
PLACES_CACHE = DATA / "places_county_cache.json"

# 11 TN pilot county FIPS -> canonical county name for logging
PILOT_COUNTIES = {
    "47007": "Bledsoe",
    "47011": "Bradley",
    "47061": "Grundy",
    "47065": "Hamilton",
    "47115": "Marion",
    "47107": "McMinn",
    "47121": "Meigs",
    "47139": "Polk",
    "47141": "Putnam",
    "47143": "Rhea",
    "47153": "Sequatchie",
}

# CDC PLACES 2024 county-level dataset.
# https://data.cdc.gov/500-Cities-Places/PLACES-Local-Data-for-Better-Health-County-Data-20/swc5-untb
PLACES_COUNTY_API = "https://data.cdc.gov/resource/swc5-untb.json"

# Map indicator display labels used in XML -> {source, api_key}. Only
# aggregation-relevant labels are listed; anything not here keeps its
# existing (possibly wrong) XML CountyValue.
#
# For PLACES: key = "short_question_text" as returned by the CDC API
# with datavaluetypeid=CrdPrv (crude prevalence, ages 18+).
PLACES_LABEL_MAP = {
    # XML label                                         CDC short_question_text (2024 release short form)
    "Diabetes (%)": "Diabetes",
    "Obesity (%)": "Obesity",
    "Asthma (%)": "Current Asthma",
    "Arthritis (%)": "Arthritis",
    "Coronary Heart Disease (%)": "Coronary Heart Disease",
    "High Blood Pressure (%)": "High Blood Pressure",
    "High Cholesterol (%)": "High Cholesterol",
    "Chronic Obstructive Pulmonary Disease (COPD) (%)": "COPD",
    "Stroke (%)": "Stroke",
    "Smoking (%)": "Current Cigarette Smoking",
    "Binge Drinking (%)": "Binge Drinking",
    "Cancer (Excluding Skin) (%)": "Cancer (non-skin) or Melanoma",
    "Poor Physical Health (≥14 Days) (%)": "Frequent Physical Distress",
    "Poor Mental Health (≥14 Days) (%)": "Frequent Mental Distress",
    "Fair/Poor Self-Reported Health (%)": "General Health",
    "Sleeping Less than 7 Hours (%)": "Short Sleep Duration",
    "Routine Checkup (%)": "Annual Checkup",
    "Dental Visit (%)": "Dental Visit",
    "Cholesterol Screening (%)": "Cholesterol Screening",
    "Colorectal Cancer Screening (%)": "Colorectal Cancer Screening",
    "Mammography (Ages 50–74) (%)": "Mammography",
    "Taking Blood Pressure Medication(%)": "High Blood Pressure Medication",
    "Taking Blood Pressure Medication (%)": "High Blood Pressure Medication",
    "No Leisure-Time Physical Activity(%)": "Physical Inactivity",
    "No Leisure-Time Physical Activity (%)": "Physical Inactivity",
    "All Teeth Lost (Ages 65+) (%)": "All Teeth Lost",
    "Uninsured (Ages 18–64) (%)": "Health Insurance",
    "Any Disability (%)": "Any Disability",
    "Hearing Disability (%)": "Hearing Disability",
    "Vision Disability (%)": "Vision Disability",
    "Cognitive Disability (%)": "Cognitive Disability",
    "Mobility Disability (%)": "Mobility Disability",
    "Self-Care Disability (%)": "Self-care Disability",
    "Independent Living Disability (%)": "Independent Living Disability",
}


def _norm_label(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def load_vendor_data():
    import pandas as pd

    df = pd.read_excel(VENDOR_XLSX, sheet_name="Export")
    df["TRACTFIPS_TL"] = (
        df["TRACTFIPS_TL"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(11)
    )
    df["_county"] = df["TRACTFIPS_TL"].str[:5]
    # normalize numeric columns
    for c in df.columns:
        if c in ("TRACTFIPS_TL", "Location", "_county"):
            continue
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def build_county_means(df, county_fips: str) -> dict:
    """Return {display_label: mean_value} for tracts in one county."""
    sub = df[df["_county"] == county_fips]
    out = {}
    for c in sub.columns:
        if c in ("TRACTFIPS_TL", "Location", "Year", "_county"):
            continue
        v = sub[c].mean()
        if v is None or (isinstance(v, float) and (v != v)):
            continue
        out[_norm_label(c)] = float(v)
    return out


def fetch_places_county(state_fips: str, county_fips3: str) -> dict:
    """Return {short_question_text: data_value} for one county from CDC.

    PLACES county API (swc5-untb) uses `locationid` (5-digit combined
    county FIPS) and `stateabbr` (2-letter). NOT `statefips` /
    `countyfips` — that's the tract-level dataset schema.
    """
    location_id = f"{state_fips}{county_fips3}"
    params = {
        "$where": f"locationid='{location_id}' AND datavaluetypeid='CrdPrv'",
        "$select": "short_question_text,data_value",
        "$limit": "500",
    }
    url = f"{PLACES_COUNTY_API}?{urllib.parse.urlencode(params, safe=' ')}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            payload = json.loads(r.read())
    except Exception as e:
        print(f"    PLACES fetch failed for {state_fips}{county_fips3}: {e}")
        return {}
    out = {}
    for row in payload:
        k = row.get("short_question_text") or ""
        v = row.get("data_value")
        if k and v is not None:
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                pass
    return out


def load_or_fetch_places_county_cache() -> dict:
    """Return {county_fips: {short_question_text: value}} for all pilot counties."""
    if PLACES_CACHE.exists():
        try:
            cache = json.loads(PLACES_CACHE.read_text())
        except Exception:
            cache = {}
    else:
        cache = {}
    changed = False
    for fips in PILOT_COUNTIES:
        if fips in cache:
            continue
        state_fips, county3 = fips[:2], fips[2:]
        print(f"  PLACES: fetching county {fips} ({PILOT_COUNTIES[fips]})...")
        cache[fips] = fetch_places_county(state_fips, county3)
        print(f"    got {len(cache[fips])} measures")
        changed = True
    if changed:
        PLACES_CACHE.write_text(json.dumps(cache, indent=2))
        print(f"  wrote {PLACES_CACHE}")
    return cache


def _fmt_value_for_xml(v, label: str) -> str:
    """Match community-profiles _fmt_xml formatting per indicator."""
    if v is None:
        return "N/A"
    if "$" in label:
        return f"${round(v):,}"
    if label.strip().endswith("(%)"):
        return f"{v:.1f}"
    if "Median Year Built" in label or label.strip() == "Median Age":
        return f"{int(round(v))}"
    if "Gini" in label:
        return f"{v:.4f}"
    return f"{v:.1f}"


def patch_one_county(
    xml_path: Path, county_fips: str, vendor_df, places_cache, dry_run: bool = False
) -> tuple[int, int, int]:
    """Return (n_acs_patched, n_places_patched, n_skipped)."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    vendor_means = build_county_means(vendor_df, county_fips)
    places_lookup = places_cache.get(county_fips, {})

    n_acs = n_places = n_skip = 0
    for ind in root.iter("Indicator"):
        name_el = ind.find("Name")
        cv_el = ind.find("CountyValue")
        if name_el is None or cv_el is None:
            continue
        label = (name_el.text or "").strip()
        if not label:
            continue

        new_value = None
        # Try PLACES first for the mapped labels
        cdc_key = PLACES_LABEL_MAP.get(label)
        if cdc_key and cdc_key in places_lookup:
            new_value = places_lookup[cdc_key]
            n_places += 1
        else:
            # Try ACS via vendor mean
            k = _norm_label(label)
            if k in vendor_means:
                new_value = vendor_means[k]
                n_acs += 1
            else:
                n_skip += 1
                continue

        formatted = _fmt_value_for_xml(new_value, label)
        cv_el.text = formatted

    if not dry_run:
        tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    return n_acs, n_places, n_skip


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--dry-run", action="store_true", help="Report changes without writing files."
    )
    args = ap.parse_args(argv)

    if not VENDOR_XLSX.exists():
        raise SystemExit(f"Vendor file missing: {VENDOR_XLSX}")

    print("Loading vendor 2024 data.xlsx ...")
    df = load_vendor_data()
    print(f"  {len(df)} tract rows, {len(df.columns)} columns")

    print("Loading / fetching PLACES county cache ...")
    places = load_or_fetch_places_county_cache()

    total = {"acs": 0, "places": 0, "skip": 0, "files": 0}
    for fips, name in PILOT_COUNTIES.items():
        # Find ALL county XMLs — community-profiles emits into both
        # TN_<County>/ and TN_<County>_InDesign_Package/. Patch BOTH so
        # whichever downstream tools read either variant see corrected values.
        candidates = list(OUTPUT_ROOT.glob(f"*/{name}_County_Community_Profiles.xml"))
        if not candidates:
            print(f"  {name} ({fips}): NO XML FOUND (skipping)")
            continue
        cty_acs = cty_places = cty_skip = 0
        for xml_path in candidates:
            n_acs, n_places, n_skip = patch_one_county(
                xml_path, fips, df, places, dry_run=args.dry_run,
            )
            cty_acs += n_acs
            cty_places += n_places
            cty_skip += n_skip
            total["files"] += 1
        total["acs"] += cty_acs
        total["places"] += cty_places
        total["skip"] += cty_skip
        marker = "(DRY)" if args.dry_run else "(written)"
        print(
            f"  {name:12} {fips}: {len(candidates)} XML(s), ACS {cty_acs} + PLACES {cty_places} patched, {cty_skip} skipped {marker}"
        )

    print("\n--- summary ---")
    print(f"XMLs processed: {total['files']}")
    print(f"ACS values patched:    {total['acs']}")
    print(f"PLACES values patched: {total['places']}")
    print(f"Indicators skipped:    {total['skip']} (no ACS + no PLACES mapping)")
    if args.dry_run:
        print("\nDry-run: no files written. Re-run without --dry-run to apply.")
    else:
        print(f"\nNext: rebuild + republish")
        print(f"  python build_rollout_dataset.py")
        print(f"  python build_arcgis_layer.py --formats gpkg")
        print(
            f"  python publish_to_arcgis.py --title 'JHFRC Tracts v11' --no-overwrite"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
