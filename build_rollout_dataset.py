"""Aggregate every built county's XML output into one tidy dataset.

Scans `../jhfrc-community-profiles/output/*_*/` for county
Community Profiles XML files (produced by the reports pipeline's
Phase 3), extracts every tract-level indicator, and emits three
format variants for downstream use:

    data/rollout_indicators.parquet   (analytics tools)
    data/rollout_indicators.csv       (Excel, Google Sheets, human reading)
    data/rollout_indicators.sqlite    (ad-hoc SQL)

Schema (one row per tract-indicator-vintage):

    state_abbr        e.g. "TN"
    county_fips       5-digit, string, leading zeros preserved
    county_name       "Sequatchie"
    tract_geoid       11-digit tract FIPS
    domain            SDoH domain (Economic / Education / ...)
    subdomain         Sub-domain
    indicator_name    "Below Poverty Line (%)"
    vintage           2024 (int; latest ACS/PLACES release)
    value             float | None (None when suppressed)
    is_suppressed     bool  (True when the report emitted "IS")
    delta_5yr         float | None (5-year change)
    delta_direction   "green" | "red" | "gray" | None
    county_avg        float | None
    state_avg         float | None
    us_avg            float | None
    source_pdf_path   relative path to the built Community Profiles PDF (if it exists)

Idempotent: overwrites the three output files on each run. Safe to
re-run whenever a new county finishes the pipeline.
"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import sys
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

try:
    import pandas as pd
    import numpy as np
except ImportError:  # pragma: no cover
    pd = None  # type: ignore
    np = None  # type: ignore


REPORTS_ROOT = Path(__file__).resolve().parent.parent / "jhfrc-community-profiles"
OUTPUT_ROOT = REPORTS_ROOT / "output"
DATA_DIR = Path(__file__).resolve().parent / "data"


def find_county_xmls(output_root: Path) -> list[Path]:
    """Return every `<County>_County_Community_Profiles.xml` in output/."""
    if not output_root.exists():
        return []
    hits = []
    for child in sorted(output_root.iterdir()):
        if not child.is_dir():
            continue
        # Skip InDesign_Package sibling folders — they mirror the primary
        # per-county folder and would double-count.
        if child.name.endswith("_InDesign_Package"):
            continue
        for xml in child.glob("*_County_Community_Profiles.xml"):
            hits.append(xml)
    return hits


def parse_county_xml(xml_path: Path) -> list[dict]:
    """Extract tract-level indicator rows from one county XML file."""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    county_name = root.attrib.get("county", "").strip()
    state_name = root.attrib.get("state", "").strip()
    state_abbr = {
        "Tennessee": "TN",
        "Georgia": "GA",
        "Alabama": "AL",
        "North Carolina": "NC",
    }.get(state_name, "")
    # Root attrib carries the 5-digit county FIPS; fall back to the
    # first profile's GEOID prefix if missing.
    county_fips = str(root.attrib.get("fips", "")).zfill(5)
    if not county_fips or county_fips == "00000":
        first_prof = root.find(".//CommunityProfile")
        if first_prof is not None:
            gid = first_prof.attrib.get("geoid", "")
            if len(gid) >= 5:
                county_fips = gid[:5]

    rows: list[dict] = []
    # The XML uses <CommunityProfile geoid="..."> — one per tract.
    for tract in root.findall(".//CommunityProfile"):
        tract_geoid = tract.attrib.get("geoid", "")
        indicators_el = tract.find("KeyCommunityIndicators")
        if indicators_el is None:
            continue
        for ind in indicators_el.findall("Indicator"):
            name = _first_text(ind, "Name")
            domain = _first_text(ind, "Domain")
            subdomain = _first_text(ind, "SubDomain")

            tract_val_el = ind.find("TractValue")
            county_val = _first_text(ind, "CountyValue")
            state_val = _first_text(ind, "StateValue")
            us_val = _first_text(ind, "USValue")

            tract_text = (
                (tract_val_el.text or "").strip() if tract_val_el is not None else ""
            )
            tract_insuff = (
                tract_val_el is not None
                and tract_val_el.attrib.get("insufficient", "") == "true"
            )
            tract_value = _parse_numeric(tract_text) if not tract_insuff else None

            delta_txt = _first_text(ind, "Delta5Year")
            delta_val = _parse_numeric(delta_txt)
            delta_direction = ind.attrib.get("deltaColor", "").strip() or None

            rows.append(
                {
                    "state_abbr": state_abbr,
                    "county_fips": county_fips,
                    "county_name": county_name,
                    "tract_geoid": tract_geoid,
                    "domain": domain,
                    "subdomain": subdomain,
                    "indicator_name": name,
                    "vintage": 2024,
                    "value": tract_value,
                    "is_suppressed": tract_insuff,
                    # delta_5yr is filled in from the XML for legacy
                    # consumers, but Brief 4 v2 escalated Phase D §1
                    # replaces it with harmonized values downstream —
                    # see apply_harmonized_deltas() below.
                    "delta_5yr": delta_val,
                    "delta_direction": delta_direction,
                    "county_avg": _parse_numeric(county_val),
                    "state_avg": _parse_numeric(state_val),
                    "us_avg": _parse_numeric(us_val),
                    "source_pdf_path": _find_pdf_for(xml_path),
                    # Trend-geography metadata (populated below when
                    # harmonized deltas are applied; None on raw XML
                    # rows and preserved for reporting).
                    "trend_geography_basis": None,
                    "trend_harmonization_method": None,
                    "trend_harmonization_coverage": None,
                    "n_source_tracts_for_delta": None,
                    # Universe (denominator) for universe-weighted tract
                    # aggregation when no <CountyValue> is published.
                    # Populated by apply_universes() from
                    # data/acs_universes.parquet. Task #123.
                    "universe": None,
                }
            )
    return rows


def _first_text(el: ET.Element, tag: str) -> str:
    child = el.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


_NUM_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


def _parse_numeric(raw: str) -> float | None:
    """Strip currency + percent + commas, then parse as float. Returns None
    for empty / NA / IS / non-numeric values."""
    if not raw:
        return None
    s = raw.strip()
    if s.upper() in {"", "NA", "N/A", "IS", "IS *"}:
        return None
    m = _NUM_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _find_pdf_for(xml_path: Path) -> str:
    """Best-effort match of the county's exported PDF (if the GA has
    exported one). Empty string if no PDF yet."""
    county_dir = xml_path.parent
    pkg_dir = county_dir.parent / f"{county_dir.name}_InDesign_Package"
    for candidate in (pkg_dir, county_dir):
        if candidate.exists():
            pdfs = sorted(candidate.glob("*.pdf"))
            if pdfs:
                return str(pdfs[0].relative_to(REPORTS_ROOT))
    return ""


def write_outputs(rows: Iterable[dict], data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    if not rows:
        print("No rows to write — nothing found in output/")
        return

    # CSV (always emitted; no third-party dep)
    csv_path = data_dir / "rollout_indicators.csv"
    fieldnames = list(rows[0].keys())
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {csv_path}  ({len(rows):,} rows)")

    # SQLite
    sqlite_path = data_dir / "rollout_indicators.sqlite"
    if sqlite_path.exists():
        sqlite_path.unlink()
    con = sqlite3.connect(sqlite_path)
    cols_ddl = ",\n  ".join(f'"{c}" TEXT' for c in fieldnames)
    con.execute(f"CREATE TABLE rollout_indicators (\n  {cols_ddl}\n);")
    placeholders = ",".join("?" * len(fieldnames))
    con.executemany(
        f"INSERT INTO rollout_indicators VALUES ({placeholders});",
        [tuple(r.get(c) for c in fieldnames) for r in rows],
    )
    # Index common query columns
    for col in ("state_abbr", "county_fips", "tract_geoid", "indicator_name", "domain"):
        con.execute(f'CREATE INDEX idx_rollout_{col} ON rollout_indicators("{col}");')
    con.commit()
    con.close()
    print(f"  wrote {sqlite_path}")

    # Parquet (requires pandas + pyarrow)
    if pd is None:
        print("  (skip parquet — pandas not installed)")
    else:
        df = pd.DataFrame(rows)
        pq_path = data_dir / "rollout_indicators.parquet"
        try:
            df.to_parquet(pq_path, index=False)
            print(f"  wrote {pq_path}")
        except Exception as e:
            print(f"  (skip parquet — {e})")


def apply_harmonized_deltas(rows: list[dict], data_dir: Path) -> None:
    """Override delta_5yr from data/harmonized_deltas.parquet.

    Brief 4 v2 escalated Phase D §1. Rows are matched by
    (tract_geoid, indicator_name). Rows without a matching harmonized
    entry keep their None delta and their trend_geography_basis stays
    'unavailable' (recorded for downstream consumers).
    """
    parquet = data_dir / "harmonized_deltas.parquet"
    if not parquet.exists():
        print(
            f"\nWARNING: {parquet.name} not found. Run\n"
            f"    python tools/harmonize_deltas.py\n"
            f"to produce it. Deltas remain unharmonized and every row\n"
            f"gets trend_geography_basis='unavailable' as a signal to\n"
            f"downstream consumers."
        )
        for r in rows:
            r["trend_geography_basis"] = "unavailable"
        return

    if pd is None:  # type: ignore[has-type]
        print(
            f"\nWARNING: pandas is not installed; cannot apply harmonized "
            f"deltas. Deltas remain unharmonized; marking rows accordingly."
        )
        for r in rows:
            r["trend_geography_basis"] = "unavailable"
        return

    print(f"\nApplying harmonized deltas from {parquet.name} ...")
    hdf = pd.read_parquet(parquet)
    # Key = (11-digit tract GEOID, indicator label). Both sides use
    # the same label conventions (came from the same 2019+2024 vendor
    # files that fed the XML pipeline).
    lookup = {
        (str(r.tract_geoid).zfill(11), r.indicator_name): r
        for r in hdf.itertuples(index=False)
    }
    n_over = n_miss = 0
    for row in rows:
        key = (row["tract_geoid"], row["indicator_name"])
        h = lookup.get(key)
        if h is None:
            n_miss += 1
            # No harmonized value — mark trend basis unavailable so
            # downstream displays honor the geography-gate default.
            row["trend_geography_basis"] = "unavailable"
            continue
        # Only override delta if a numeric value came out of the
        # harmonization (both 2019 and 2024 sides had a value).
        d = h.delta_5yr_harmonized
        if d is not None and not (isinstance(d, float) and np.isnan(d)):
            row["delta_5yr"] = float(d)
        row["trend_geography_basis"] = h.trend_geography_basis
        row["trend_harmonization_method"] = h.trend_harmonization_method
        row["trend_harmonization_coverage"] = (
            float(h.trend_harmonization_coverage)
            if h.trend_harmonization_coverage is not None
            else None
        )
        row["n_source_tracts_for_delta"] = (
            int(h.n_source_tracts) if h.n_source_tracts is not None else None
        )
        n_over += 1
    print(
        f"  matched + overrode delta_5yr: {n_over:,} rows\n"
        f"  no harmonized value found:    {n_miss:,} rows (kept XML delta + marked unavailable)"
    )


def apply_universes(rows: list[dict], data_dir: Path) -> None:
    """Attach per-(tract, indicator) universe values to each row.

    Reads data/acs_universes.parquet (produced by
    tools/pull_acs_universes.py) and data/dictionary.json (for the
    indicator label -> short_id map). Each row's "universe" slot is
    populated when a matching (tract_geoid, short_id) row exists in
    the parquet; otherwise left None. Downstream:
    build_arcgis_layer.py pivots this into <short>_univ so the
    dashboard can do universe-weighted county aggregation as a
    fallback when the published <CountyValue> is missing. Task #123.
    """
    parquet = data_dir / "acs_universes.parquet"
    dict_path = data_dir / "dictionary.json"
    if not parquet.exists():
        print(
            f"\nNOTE: {parquet.name} not found. Skipping universe join. "
            f"Run tools/pull_acs_universes.py to produce it."
        )
        return
    if pd is None:  # type: ignore[has-type]
        print(f"\nNOTE: pandas unavailable; skipping universe join.")
        return
    if not dict_path.exists():
        print(f"\nNOTE: {dict_path.name} not found; skipping universe join.")
        return

    import json as _json

    d = _json.loads(dict_path.read_text())

    # Normalize labels on both sides for the JOIN KEY ONLY: lowercase,
    # then strip every non-alphanumeric character. XML and dictionary
    # labels diverge on whitespace ("Medication(%)" vs "Medication (%)"),
    # unicode dashes ("16-19" vs "16–19"), and inequality symbols
    # ("Paying >=30%" vs "Paying ≥30%"). Alphanumeric-only makes
    # every variant reduce to the same key. The original label text is
    # preserved everywhere else.
    import re as _re

    def _norm_label(s):
        return _re.sub(r"[^a-z0-9]+", "", (s or "").lower())

    label_to_short: dict[str, str] = {}
    for short, entry in d.get("indicators", {}).items():
        label = entry.get("label")
        if label:
            label_to_short[_norm_label(label)] = short

    print(f"\nAttaching universes from {parquet.name} ...")
    udf = pd.read_parquet(parquet)
    lookup: dict[tuple[str, str], float] = {}
    for r in udf.itertuples(index=False):
        u = r.universe
        if u is None or (isinstance(u, float) and np.isnan(u)):
            continue
        lookup[(str(r.tract_geoid).zfill(11), str(r.indicator_id))] = float(u)

    n_matched = n_no_recipe = n_no_data = 0
    for row in rows:
        short = label_to_short.get(_norm_label(row["indicator_name"]))
        if not short:
            n_no_recipe += 1
            continue
        val = lookup.get((row["tract_geoid"], short))
        if val is None:
            n_no_data += 1
            continue
        row["universe"] = val
        n_matched += 1
    print(
        f"  matched: {n_matched:,} rows | "
        f"no recipe: {n_no_recipe:,} | no data: {n_no_data:,}"
    )


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Aggregate per-county XML outputs into a tidy dataset."
    )
    ap.add_argument(
        "--output-root",
        type=Path,
        default=OUTPUT_ROOT,
        help=f"Reports project's output/ folder (default: {OUTPUT_ROOT}).",
    )
    ap.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
        help=f"Where to write the three variant files (default: {DATA_DIR}).",
    )
    args = ap.parse_args(argv)

    xmls = find_county_xmls(args.output_root)
    print(f"Found {len(xmls)} county XML file(s) in {args.output_root}")
    all_rows: list[dict] = []
    for x in xmls:
        n_before = len(all_rows)
        all_rows.extend(parse_county_xml(x))
        n_added = len(all_rows) - n_before
        print(f"  {x.name}: {n_added} rows")

    # Brief 4 v2 escalated Phase D §1: override the XML-sourced
    # delta_5yr with geography-harmonized values from
    # data/harmonized_deltas.parquet (produced by tools/harmonize_deltas.py).
    # The XML deltas were computed by joining ACS 2015-19 (2010 tract
    # vintage) to 2020-24 (2020 tract vintage) via GEOID string with no
    # harmonization — invalid for any tract whose physical boundary
    # differs across the two vintages. The parquet re-projects 2019
    # values onto 2020 geometry via areal apportionment (or primary-
    # overlap for medians) and computes fresh deltas.
    apply_harmonized_deltas(all_rows, args.data_dir)

    # Task #123: attach per-tract universe values so build_arcgis_layer
    # can emit <indicator>_univ fields and the dashboard can do
    # universe-weighted aggregation when <CountyValue> is missing.
    apply_universes(all_rows, args.data_dir)

    write_outputs(all_rows, args.data_dir)

    # Quick summary
    if all_rows:
        n_counties = len({r["county_fips"] for r in all_rows})
        n_tracts = len({r["tract_geoid"] for r in all_rows})
        n_inds = len({r["indicator_name"] for r in all_rows})
        n_supp = sum(1 for r in all_rows if r["is_suppressed"])
        print(
            f"\nSummary: {n_counties} counties, {n_tracts} tracts, "
            f"{n_inds} distinct indicators, "
            f"{n_supp:,} IS-suppressed cells "
            f"({n_supp / len(all_rows) * 100:.1f}%)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
