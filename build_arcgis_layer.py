"""Join the rollout dataset to TIGER/Line tract polygons and emit a
map-ready file for ArcGIS Online.

Inputs:
    data/rollout_indicators.parquet OR data/rollout_indicators.csv
        (produced by build_rollout_dataset.py)
    ../jhfrc-community-profiles/data/census_tracts.gpkg
        (47-county subset of TIGER/Line tract polygons the reports
        pipeline already ships)

Output:
    data/jhfrc_tracts.gpkg       (primary, one layer per state or one merged)
    data/jhfrc_tracts.shp        (optional; ArcGIS Online accepts either)
    data/jhfrc_tracts.geojson    (optional; useful for QA in a browser)

Attribute strategy:
    - Long-form dataset has one row per tract-indicator.
    - Feature Layers work best with one row per tract, indicators as columns.
    - We pivot to WIDE: 1 row per tract, ~40 headline indicators as attribute
      columns. The full 93-indicator dataset stays in the Parquet/CSV/SQLite
      Tier 1 files for anyone who wants the deep cut.

Field naming:
    - Esri Shapefile limits field names to 10 chars. When exporting to
      Shapefile we use the short-form ids from HEADLINE_INDICATORS below;
      when exporting to GeoPackage (no such limit) we use human labels.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
DATA_DIR = REPO / "data"
REPORTS_ROOT = REPO.parent / "jhfrc-community-profiles"
TIGER_GPKG = REPORTS_ROOT / "data" / "census_tracts.gpkg"


# 40 headline indicators the Dashboard will surface out of the ~93 in
# the full dataset. Ordered by SDoH domain. Short_id is the Shapefile
# 10-char field name; label is the human-readable name from the
# reports pipeline's XML output.
HEADLINE_INDICATORS: list[tuple[str, str]] = [
    # Labels MUST match exactly what appears in the source XML
    # (indicator names include unicode dashes/percent signs). If a
    # label doesn't match, the pivot silently drops the indicator.
    # Economic
    ("pov_below", "Below Poverty Line (%)"),
    ("hh_snap", "Households Receiving Food Stamps (%)"),
    ("hh_pubasst", "Households Receiving Public Assistance (%)"),
    ("emp_adults", "Employed Adults (%)"),
    ("not_labor", "Not in Labor Force (%)"),
    ("mhi", "Median Household Income ($)"),
    ("mpci", "Mean Per Capita Income ($)"),
    ("gini", "Gini Index (Income Inequality)"),
    # Education
    ("edu_lths", "Less than High School Education (%)"),
    ("edu_posths", "Any Post-High School Education (%)"),
    ("edu_assoc", "Associate's Degree (%)"),
    ("edu_ba", "Bachelor's Degree (%)"),
    ("edu_grad", "Graduate/Professional Degree (%)"),
    ("youth_dis", "Teens (Ages 16–19) Not in School & Unemployed (%)"),
    # Healthcare — coverage
    ("any_disab", "Any Disability (%)"),
    ("no_insur", "Uninsured (Ages 18–64) (%)"),
    ("private_ins", "Private Insurance (All Ages) (%)"),
    ("medicaid", "Medicaid Coverage (All Ages) (%)"),
    # Healthcare — conditions
    ("hh_diab", "Diabetes (%)"),
    ("hh_asthma", "Asthma (%)"),
    ("hh_heart", "Coronary Heart Disease (%)"),
    ("hh_bp", "High Blood Pressure (%)"),
    ("hh_bpmed", "Taking Blood Pressure Medication(%)"),
    ("hh_chol", "High Cholesterol (%)"),
    ("hh_arthr", "Arthritis (%)"),
    ("hh_copd", "Chronic Obstructive Pulmonary Disease (COPD) (%)"),
    ("hh_stroke", "Stroke (%)"),
    # Healthcare — self-reported + behaviors
    ("ph_poor14", "Poor Physical Health (≥14 Days) (%)"),
    ("mh_poor14", "Poor Mental Health (≥14 Days) (%)"),
    ("fair_hlth", "Fair/Poor Self-Reported Health (%)"),
    ("smoke", "Smoking (%)"),
    ("binge", "Binge Drinking (%)"),
    ("no_activ", "No Leisure-Time Physical Activity(%)"),
    ("obesity", "Obesity (%)"),
    ("sleep_lt7", "Sleeping Less than 7 Hours (%)"),
    # Physical Infrastructure — housing
    ("med_rent", "Median Gross Rent ($)"),
    ("med_home", "Median Home Value ($)"),
    ("owner_occ", "Owner-Occupied Households (%)"),
    ("renter_occ", "Renter-Occupied Households (%)"),
    ("vacant", "Vacant Housing Units (%)"),
    ("cost_owner", "Owners Paying ≥30% of Income (%)"),
    ("cost_rent", "Renters Paying ≥30% of Income (%)"),
    ("housing_old", "Housing Built Before 1979 (%)"),
    # Physical Infrastructure — digital + transportation
    ("bb_access", "Households with Broadband Access (%)"),
    ("no_intnet", "Households without Internet Access (%)"),
    ("no_veh", "Households without a Vehicle (%)"),
    ("transit", "Public Transit Commuters (%)"),
    ("walk", "Workers Walking to Work (%)"),
    # Social — age
    ("age_65p", "Population Age 65+ (%)"),
    ("age_18_64", "Population Age 18–64 (%)"),
    ("med_age", "Median Age"),
    # Social — households
    ("single_p", "Single-Parent Families (%)"),
    ("live_alon_65", "Age 65+ Living Alone (%)"),
    ("hh_size", "Average Household Size"),
    ("married", "Married (%)"),
    # Social — race / ethnicity / language
    ("hisp", "Hispanic (%)"),
    ("black", "Black / African American (%)"),
    ("white", "White (%)"),
    ("asian", "Asian (%)"),
    ("foreign_born", "Foreign Born Population (%)"),
    ("lang_span", "Spanish Speakers (Age 5+) (%)"),
]


SHAPEFILE_FIELD_ALIASES = {
    "foreign_born": "foreign",
    "foreign_born_d5": "foreign_d5",
    "foreign_born_supp": "frgn_supp",
    # The <indicator>_county / _state / _us fan-out would blow the
    # 10-char Shapefile field limit for the longer short_ids. Alias
    # them to shipped-friendly names; GPKG/GeoJSON keep the full
    # descriptive form.
    "foreign_born_county": "frgn_cnty",
    "foreign_born_state": "frgn_st",
    "foreign_born_us": "frgn_us",
    "hh_pubasst_county": "hhpb_cnty",
    "hh_pubasst_state": "hhpb_st",
    "hh_pubasst_us": "hhpb_us",
    "edu_posths_county": "edpt_cnty",
    "edu_posths_state": "edpt_st",
    "edu_posths_us": "edpt_us",
    "housing_old_county": "hous_cnty",
    "housing_old_state": "hous_st",
    "housing_old_us": "hous_us",
    "live_alon_65_county": "la65_cnty",
    "live_alon_65_state": "la65_st",
    "live_alon_65_us": "la65_us",
    "private_ins_county": "prin_cnty",
    "private_ins_state": "prin_st",
    "private_ins_us": "prin_us",
}


def load_rollout() -> "pd.DataFrame":  # type: ignore  # noqa: F821
    import pandas as pd

    pq = DATA_DIR / "rollout_indicators.parquet"
    csv = DATA_DIR / "rollout_indicators.csv"
    if pq.exists():
        return pd.read_parquet(pq)
    if csv.exists():
        return pd.read_csv(csv, dtype={"county_fips": str, "tract_geoid": str})
    raise SystemExit(f"No rollout dataset found. Run build_rollout_dataset.py first.")


def load_tracts() -> "gpd.GeoDataFrame":  # type: ignore  # noqa: F821
    import geopandas as gpd

    if not TIGER_GPKG.exists():
        raise SystemExit(
            f"TIGER tract polygons missing at {TIGER_GPKG}. Ensure the "
            f"reports project is a sibling directory."
        )
    gdf = gpd.read_file(TIGER_GPKG)
    # Standardize GEOID column name
    for cand in ("GEOID", "GEOID20", "GEOID_TRACT_20", "geoid"):
        if cand in gdf.columns:
            gdf = gdf.rename(columns={cand: "tract_geoid"})
            break
    gdf["tract_geoid"] = gdf["tract_geoid"].astype(str).str.zfill(11)
    return gdf[["tract_geoid", "geometry"]]


def wide_pivot(long_df: "pd.DataFrame") -> "pd.DataFrame":  # type: ignore  # noqa: F821
    import pandas as pd

    keep_cols = [
        "state_abbr",
        "county_fips",
        "county_name",
        "tract_geoid",
    ]
    label_to_short = {label: short for short, label in HEADLINE_INDICATORS}

    # Keep only headline indicators, drop suppressed cells (they become NaN).
    hl = long_df[long_df["indicator_name"].isin(label_to_short)].copy()
    hl.loc[hl["is_suppressed"] == True, "value"] = None  # noqa: E712
    hl["short"] = hl["indicator_name"].map(label_to_short)

    # Pivot to wide (one row per tract; each indicator becomes a column)
    wide = hl.pivot_table(
        index=keep_cols, columns="short", values="value", aggfunc="first",
    ).reset_index()
    # Add a delta column per indicator (short_id + "_d5")
    d5 = hl.pivot_table(
        index=keep_cols, columns="short", values="delta_5yr", aggfunc="first",
    ).reset_index()
    d5 = d5.rename(columns={c: f"{c}_d5" for c in d5.columns if c not in keep_cols})
    wide = wide.merge(d5, on=keep_cols, how="left")
    # Add suppression flags per indicator (short_id + "_supp") — bool
    supp = (
        long_df[long_df["indicator_name"].isin(label_to_short)]
        .assign(short=lambda x: x["indicator_name"].map(label_to_short))
        .pivot_table(
            index=keep_cols, columns="short", values="is_suppressed", aggfunc="first",
        )
        .reset_index()
    )
    supp = supp.rename(
        columns={c: f"{c}_supp" for c in supp.columns if c not in keep_cols}
    )
    wide = wide.merge(supp, on=keep_cols, how="left")
    # Add published county / state / US benchmark values per indicator
    # (short_id + "_county" / "_state" / "_us"). Sourced from the
    # community-profiles XML's <CountyValue>/<StateValue>/<USValue>
    # per Indicator block -- these are the authoritative published
    # numbers, not derived from tract aggregation. Task #118.
    for src_col, suffix in (
        ("county_avg", "_county"),
        ("state_avg", "_state"),
        ("us_avg", "_us"),
    ):
        bench = hl.pivot_table(
            index=keep_cols, columns="short", values=src_col, aggfunc="first",
        ).reset_index()
        bench = bench.rename(
            columns={c: f"{c}{suffix}" for c in bench.columns if c not in keep_cols}
        )
        wide = wide.merge(bench, on=keep_cols, how="left")
    return wide


def emit_arcgis_layer(formats: list[str] = ["gpkg", "shp", "geojson"],) -> None:
    import geopandas as gpd

    long_df = load_rollout()
    print(f"Loaded rollout: {len(long_df):,} rows")

    tracts = load_tracts()
    print(f"Loaded TIGER polygons: {len(tracts):,} tracts")

    wide = wide_pivot(long_df)
    print(f"Wide pivot: {len(wide):,} tracts x {wide.shape[1]} columns")

    joined = tracts.merge(wide, on="tract_geoid", how="inner")
    print(f"Joined to polygons: {len(joined):,} tracts")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    joined = joined.to_crs(4326)

    if "gpkg" in formats:
        p = DATA_DIR / "jhfrc_tracts.gpkg"
        if p.exists():
            p.unlink()
        joined.to_file(p, driver="GPKG", layer="jhfrc_tracts")
        print(f"  wrote {p}")
    if "geojson" in formats:
        p = DATA_DIR / "jhfrc_tracts.geojson"
        if p.exists():
            p.unlink()
        joined.to_file(p, driver="GeoJSON")
        print(f"  wrote {p}")
    if "shp" in formats:
        # Shapefile has a 10-char field name limit; our headline short_ids
        # are all <=10 chars so this is safe.
        p = DATA_DIR / "jhfrc_tracts.shp"
        shp_joined = joined.rename(columns=SHAPEFILE_FIELD_ALIASES)
        shp_joined.to_file(p, driver="ESRI Shapefile")
        print(f"  wrote {p}  (+ .shx .dbf .prj .cpg)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Join the rollout dataset to TIGER tract polygons + emit for ArcGIS Online."
    )
    ap.add_argument(
        "--formats",
        nargs="+",
        default=["gpkg", "shp", "geojson"],
        choices=["gpkg", "shp", "geojson"],
        help="Output formats to emit (default: all three).",
    )
    args = ap.parse_args(argv)
    emit_arcgis_layer(formats=args.formats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
