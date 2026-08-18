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
except ImportError:  # pragma: no cover
    pd = None  # type: ignore


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
                    "delta_5yr": delta_val,
                    "delta_direction": delta_direction,
                    "county_avg": _parse_numeric(county_val),
                    "state_avg": _parse_numeric(state_val),
                    "us_avg": _parse_numeric(us_val),
                    "source_pdf_path": _find_pdf_for(xml_path),
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
