"""Compare tract-derived county estimates against official ACS county
estimates for aggregation-eligible indicators. Task #123 step 9.

For every indicator whose dictionary entry has
    aggregation.method == "universe_weighted"
this script:

  1. Loads the current GPKG (data/jhfrc_tracts.gpkg) and computes the
     universe-weighted county estimate as
         sum(tract_rate * tract_universe) / sum(tract_universe)
     — identical formula to the dashboard's _countyValue Path 2.

  2. Pulls the official ACS 5-year county-level value for the same
     indicator + vintage from the Census API (S-table subject data
     endpoint or B-table detail data), using the ACS_TABLE mapping
     below.

  3. Prints per-(indicator, county) diff: derived vs official, absolute
     and percent difference. Flags anything > 10% relative or > 2 pp
     absolute as SUSPECT.

Reads:
  data/jhfrc_tracts.gpkg
  data/dictionary.json (for aggregation eligibility)
  env CENSUS_API_KEY

The ACS_TABLE mapping below is the minimum viable coverage — a
follow-up should expand it once source_table + source_statistic are
codified per-indicator in dictionary.json (see #123 recommended rule).

Usage:
    python tools/validate_aggregation.py
    python tools/validate_aggregation.py --tolerance-pp 1.0 --tolerance-pct 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
GPKG = DATA / "jhfrc_tracts.gpkg"
DICT_PATH = DATA / "dictionary.json"
DEFAULT_YEAR = 2024  # ACS 5-year 2020-2024 release

# Minimum viable indicator -> official ACS county estimate mapping.
# Each entry names the ACS 5-year DP/S-table variable that IS the
# published county percent (or dollar) for that indicator. Structure:
#   {short_id: {"var": "DP03_0119PE", "kind": "percent" | "currency"}}
# kind is a hint for tolerance selection.
#
# NOTE: The correct DP/S variables depend on the exact community-
# profiles source statistic. This mapping is a first pass — extend
# as we verify each numerator/denominator against the profile PDFs.
ACS_TABLE = {
    "pov_below": {"var": "DP03_0119PE", "kind": "percent"},  # % below poverty
    "hh_snap": {"var": "DP03_0074PE", "kind": "percent"},  # HHs with SNAP
    "hh_pubasst": {
        "var": "DP03_0072PE",
        "kind": "percent",
    },  # HHs with public assistance income
    "emp_adults": {"var": "DP03_0004PE", "kind": "percent"},  # Employment rate 16+
    "not_labor": {"var": "DP03_0007PE", "kind": "percent"},  # Not in labor force
    "mpci": {"var": "DP03_0088E", "kind": "currency"},  # Per capita income
    "edu_lths": {"var": "S1501_C02_014E", "kind": "percent"},  # < HS
    "edu_ba": {"var": "S1501_C02_015E", "kind": "percent"},  # BA or higher
    "no_veh": {"var": "DP04_0058PE", "kind": "percent"},  # No vehicle available
    "vacant": {"var": "DP04_0003PE", "kind": "percent"},  # Vacant units
    "housing_old": {"var": "DP04_0026PE", "kind": "percent"},  # Built 1979 or earlier
    "bb_access": {"var": "DP02_0154PE", "kind": "percent"},  # Broadband
    "cost_rent": {"var": "DP04_0142PE", "kind": "percent"},  # Renters paying 30%+
    "cost_owner": {
        "var": "DP04_0114PE",
        "kind": "percent",
    },  # Owners with mortgage paying 30%+
    "single_p": {"var": "S1101_C01_014E", "kind": "percent"},  # Single-parent
    "lang_span": {"var": "S1601_C02_005E", "kind": "percent"},  # Spanish spoken at home
}

STATE_ABBR_TO_FIPS = {"TN": "47", "GA": "13", "AL": "01", "NC": "37"}


def load_dict() -> dict:
    return json.loads(DICT_PATH.read_text())


def eligible_indicators(d: dict) -> list[str]:
    out = []
    for ind_id, entry in d.get("indicators", {}).items():
        agg = entry.get("aggregation") or {}
        if agg.get("method") == "universe_weighted":
            out.append(ind_id)
    return sorted(out)


def derived_county_estimate(
    gdf, county_fips: str, ind_id: str, min_coverage: float = 0.80
) -> float | None:
    """Reproduce the dashboard's _countyValue Path 2 exactly."""
    val_col = ind_id
    univ_col = ind_id + "_univ"
    if val_col not in gdf.columns or univ_col not in gdf.columns:
        return None
    sub = gdf[gdf["county_fips"] == county_fips]
    if not len(sub):
        return None
    mask = sub[val_col].notna() & sub[univ_col].notna() & (sub[univ_col] > 0)
    n_valid = int(mask.sum())
    n_total = len(sub)
    coverage = n_valid / n_total if n_total else 0.0
    if coverage < min_coverage:
        return None
    r = sub.loc[mask, val_col].astype(float)
    u = sub.loc[mask, univ_col].astype(float)
    w = u.sum()
    return float((r * u).sum() / w) if w > 0 else None


def official_county_estimate(
    api_key: str,
    state_fips: str,
    county_fips3: str,
    acs_var: str,
    year: int = DEFAULT_YEAR,
) -> float | None:
    """Query the ACS DP/S table at county level for one variable."""
    # DP tables live at /profile, S tables at /subject.
    if acs_var.startswith("DP"):
        endpoint = f"https://api.census.gov/data/{year}/acs/acs5/profile"
    elif acs_var.startswith("S"):
        endpoint = f"https://api.census.gov/data/{year}/acs/acs5/subject"
    else:
        endpoint = f"https://api.census.gov/data/{year}/acs/acs5"
    params = {
        "get": acs_var,
        "for": f"county:{county_fips3}",
        "in": f"state:{state_fips}",
        "key": api_key,
    }
    url = f"{endpoint}?{urllib.parse.urlencode(params, safe=':,*')}"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            payload = json.loads(r.read())
    except Exception as e:
        return None
    if not payload or len(payload) < 2:
        return None
    header, row = payload[0], payload[1]
    try:
        idx = header.index(acs_var)
    except ValueError:
        return None
    cell = row[idx]
    try:
        v = float(cell)
        # ACS jam values (-666666666 etc.) signal suppression; skip.
        return None if v < -1000 else v
    except (TypeError, ValueError):
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--tolerance-pp",
        type=float,
        default=2.0,
        help="Percentage-point tolerance for percent indicators (default 2.0).",
    )
    ap.add_argument(
        "--tolerance-pct",
        type=float,
        default=10.0,
        help="Relative tolerance (percent) for currency (default 10.0).",
    )
    args = ap.parse_args(argv)

    api_key = os.environ.get("CENSUS_API_KEY")
    if not api_key:
        raise SystemExit("CENSUS_API_KEY not set.")

    import geopandas as gpd

    gdf = gpd.read_file(GPKG)
    d = load_dict()

    # Distinct counties in the pilot (from the layer).
    counties = sorted(
        (r.county_fips, r.county_name)
        for r in gdf[["county_fips", "county_name"]]
        .drop_duplicates()
        .itertuples(index=False)
    )
    print(f"Pilot counties: {len(counties)}")

    eligible = eligible_indicators(d)
    print(f"Aggregation-eligible indicators: {len(eligible)}")
    print(f"With ACS_TABLE mapping:          {len(set(eligible) & set(ACS_TABLE))}\n")

    rows = []
    for ind_id in eligible:
        if ind_id not in ACS_TABLE:
            continue
        mapping = ACS_TABLE[ind_id]
        for county_fips, county_name in counties:
            state_fips = county_fips[:2]
            county3 = county_fips[2:]
            derived = derived_county_estimate(gdf, county_fips, ind_id)
            official = official_county_estimate(
                api_key, state_fips, county3, mapping["var"],
            )
            if derived is None and official is None:
                continue
            diff_abs = (
                (derived - official)
                if (derived is not None and official is not None)
                else None
            )
            diff_rel = (
                (100 * diff_abs / official)
                if (diff_abs is not None and official)
                else None
            )
            flag = ""
            if diff_abs is not None:
                if mapping["kind"] == "percent" and abs(diff_abs) > args.tolerance_pp:
                    flag = "SUSPECT"
                elif (
                    mapping["kind"] == "currency"
                    and diff_rel is not None
                    and abs(diff_rel) > args.tolerance_pct
                ):
                    flag = "SUSPECT"
            rows.append(
                {
                    "indicator": ind_id,
                    "county": county_name,
                    "derived": derived,
                    "official": official,
                    "diff_abs": diff_abs,
                    "diff_rel_pct": diff_rel,
                    "flag": flag,
                    "acs_var": mapping["var"],
                }
            )

    # Print per-indicator summary
    print(
        f"{'indicator':14} {'county':12} {'derived':>10} {'official':>10} {'diff':>8} {'diff%':>7} {'flag':>8}"
    )
    print("-" * 80)
    for r in rows:
        d_ = "" if r["derived"] is None else f"{r['derived']:.2f}"
        o_ = "" if r["official"] is None else f"{r['official']:.2f}"
        da = "" if r["diff_abs"] is None else f"{r['diff_abs']:+.2f}"
        dr = "" if r["diff_rel_pct"] is None else f"{r['diff_rel_pct']:+.1f}%"
        print(
            f"{r['indicator']:14} {r['county']:12} {d_:>10} {o_:>10} {da:>8} {dr:>7} {r['flag']:>8}"
        )

    n_suspect = sum(1 for r in rows if r["flag"] == "SUSPECT")
    print(f"\nTotal SUSPECT rows: {n_suspect} / {len(rows)}")

    # Also emit CSV for diffing over time
    import csv

    out = DATA / "validate_aggregation.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=list(rows[0].keys())
            if rows
            else [
                "indicator",
                "county",
                "derived",
                "official",
                "diff_abs",
                "diff_rel_pct",
                "flag",
                "acs_var",
            ],
        )
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
