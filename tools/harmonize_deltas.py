"""Compute tract-level 5-year deltas using harmonized 2015-2019 → 2020
tract geography, in one step and without triggering the community-
profiles PDF/image pipeline.

Brief 4 v2 escalated Phase D §1. The community-profiles project (a
sibling repo) fetches ACS 2015-2019 (2010 tract vintage) and 2020-2024
(2020 tract vintage), joins them by GEOID string, and writes deltas
into per-county XML files. That join is silently invalid for any tract
whose physical boundary differs between 2010 and 2020. This tool by-
passes that shortcut. It:

  1. Reads the two vendor Excel files directly:
       jhfrc-community-profiles/data/2019 data.xlsx  (2010 vintage)
       jhfrc-community-profiles/data/2024 data.xlsx  (2020 vintage)

  2. Uses src/utils/tract_harmonize.py (also in the sibling repo) to
     re-project every 2019 tract value onto 2020 tract geography via
     areal apportionment based on the Census 2020↔2010 tract
     relationship files (data/geo/tract_2020_to_2010_rel_stFIPS.txt).

  3. Computes harmonized_delta = 2024_value - harmonized_2019_value
     for each (2020 tract, indicator) pair.

  4. Emits data/harmonized_deltas.parquet with columns:
       county_fips, tract_geoid, indicator_name, delta_5yr_harmonized,
       trend_geography_basis, trend_harmonization_method,
       trend_harmonization_coverage, n_source_tracts

Downstream:
  build_rollout_dataset.py should load this and OVERRIDE the
  delta_5yr column (which was pulled from the XML's Delta5Year and is
  invalid). Metadata columns propagate through.

Idempotent. Cached input files only. Never runs Selenium, PyMuPDF,
InDesign, or POI pulls.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
COMMUNITY = REPO.parent / "jhfrc-community-profiles"
COMMUNITY_DATA = COMMUNITY / "data"

# The pilot's four service-area states — determines which Census
# relationship files we need. Kept explicit so we notice when the
# pilot expands.
PILOT_STATE_FIPS = ["47", "13", "01", "37"]  # TN, GA, AL, NC

# Median / Gini indicators — areal apportionment of a median is
# arithmetically invalid, so these use primary-overlap (take the value
# from the largest-area 2010 tract). See tract_harmonize.py docstring.
MEDIAN_LIKE_KEYWORDS = ("median", "gini", "mean per capita income")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _load_vendor(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="Export")
    df["GEOID"] = (
        df["TRACTFIPS_TL"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(11)
    )
    return df


def _indicator_columns(df: pd.DataFrame) -> list[str]:
    """Numeric ACS columns (rate + median), excluding identifiers."""
    skip = {
        "TRACTFIPS_TL",
        "GEOID",
        "STATE_FIPS",
        "STATE",
        "COUNTY_FIPS",
        "COUNTY",
        "TRACT",
        "NAME",
        "REGION",
    }
    return [
        c for c in df.columns if c not in skip and pd.api.types.is_numeric_dtype(df[c])
    ]


def _is_median_like(label: str) -> bool:
    n = _norm(label)
    return any(k in n for k in MEDIAN_LIKE_KEYWORDS)


def build_harmonized_deltas(counties: list[str] | None = None) -> pd.DataFrame:
    """Return a long-form DataFrame of harmonized 5-year deltas.

    Rows: (county_fips × 2020 tract × indicator).
    Columns: county_fips, tract_geoid, indicator_name,
             value_2024, value_2019_harmonized, delta_5yr_harmonized,
             trend_geography_basis, trend_harmonization_method,
             trend_harmonization_coverage, n_source_tracts
    """
    # Late import so this file can document itself even if the sibling
    # repo isn't on sys.path.
    if str(COMMUNITY) not in sys.path:
        sys.path.insert(0, str(COMMUNITY))
    from src.utils.tract_harmonize import (  # type: ignore
        harmonize_series,
        harmonize_primary_overlap,
        load_rel_file,
    )

    d19 = _load_vendor(COMMUNITY_DATA / "2019 data.xlsx")
    d24 = _load_vendor(COMMUNITY_DATA / "2024 data.xlsx")

    # Common ACS indicators (by column name) between the two files.
    common_cols = sorted(set(_indicator_columns(d19)) & set(_indicator_columns(d24)))
    print(f"[harmonize] common ACS indicator columns: {len(common_cols)}")
    if not common_cols:
        raise SystemExit(
            "no common indicator columns — schema drift between 2019 and 2024 files?"
        )

    d19_idx = d19.set_index("GEOID")
    d24_idx = d24.set_index("GEOID")

    # Load all state rel files ONCE, keyed by state FIPS.
    rel_by_state = {st: load_rel_file(st) for st in PILOT_STATE_FIPS}

    # Which counties to process? Default to every county present in the
    # 2024 file (which is authoritative for 2020 tract geography).
    all_counties = sorted({g[:5] for g in d24_idx.index if len(g) >= 5})
    if counties:
        all_counties = [c for c in all_counties if c in set(counties)]
    print(f"[harmonize] processing {len(all_counties)} counties")

    rows = []
    for county_fips in all_counties:
        state_fips = county_fips[:2]
        rel = rel_by_state.get(state_fips)
        if rel is None:
            print(
                f"[harmonize] skipping county {county_fips} — no rel file for state {state_fips}"
            )
            continue
        for col in common_cols:
            s19 = d19_idx[col].astype(float, errors="ignore")
            method_fn = (
                harmonize_primary_overlap if _is_median_like(col) else harmonize_series
            )
            method_name = (
                "primary_overlap_2010" if _is_median_like(col) else "areal_2010_to_2020"
            )
            harm = method_fn(s19, rel, county_fips)
            if harm.empty:
                continue
            # Attach 2024 values on the 2020 tract index (same GEOID space)
            joined = harm.join(d24_idx[col].rename("value_2024"), how="left")
            joined["value_2019_harmonized"] = joined["harmonized_value"]
            joined["delta_5yr_harmonized"] = (
                joined["value_2024"] - joined["value_2019_harmonized"]
            )
            for tract_geoid, r in joined.iterrows():
                rows.append(
                    {
                        "county_fips": county_fips,
                        "tract_geoid": tract_geoid,
                        "indicator_name": col,
                        "value_2024": r.value_2024,
                        "value_2019_harmonized": r.value_2019_harmonized,
                        "delta_5yr_harmonized": r.delta_5yr_harmonized,
                        "trend_geography_basis": "harmonized_2020_tract",
                        "trend_harmonization_method": method_name,
                        "trend_harmonization_coverage": r.coverage,
                        "n_source_tracts": int(r.n_source_tracts)
                        if pd.notna(r.n_source_tracts)
                        else 0,
                    }
                )
    out = pd.DataFrame(rows)
    print(f"[harmonize] emitted {len(out):,} rows")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compute harmonized 5-year tract deltas.")
    ap.add_argument(
        "--counties",
        nargs="+",
        default=None,
        help="County FIPS to include (default: all counties in the 2024 vendor file).",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=DATA / "harmonized_deltas.parquet",
        help="Output parquet path.",
    )
    args = ap.parse_args(argv)

    df = build_harmonized_deltas(counties=args.counties)
    if df.empty:
        raise SystemExit("no harmonized rows produced")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)
    print(f"wrote {args.out}  ({args.out.stat().st_size:,} bytes)")

    # Also emit a small summary CSV alongside for eyeballing.
    summary_path = args.out.with_suffix(".summary.csv")
    (
        df.groupby("county_fips")
        .agg(
            rows=("tract_geoid", "count"),
            tracts=("tract_geoid", "nunique"),
            indicators=("indicator_name", "nunique"),
            cov_min=("trend_harmonization_coverage", "min"),
            cov_mean=("trend_harmonization_coverage", "mean"),
            missing_2024=("value_2024", lambda s: int(s.isna().sum())),
            missing_2019=("value_2019_harmonized", lambda s: int(s.isna().sum())),
        )
        .to_csv(summary_path)
    )
    print(f"wrote {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
