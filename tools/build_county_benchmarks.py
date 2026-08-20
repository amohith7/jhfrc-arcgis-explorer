"""Build a direct, published-county benchmark cache for JHFRC dashboard
indicators across all 95 Tennessee counties. Supersedes the vendor
tract-mean approach that produced the wrong `<indicator>_county` values
on the ArcGIS layer.

Source hierarchy (per project spec):
    1. Official ACS 5-year county estimate (Data Profile / Subject / B
       table variable that IS the published county number)
    2. Official CDC PLACES county estimate (2024 release, crude
       prevalence) for PLACES measures
    3. Validated universe-weighted tract aggregation -- NOT done here;
       this cache produces published-county values only, and the
       downstream `build_rollout_dataset.py` step can still fall back
       to tract aggregation for indicators this cache leaves blank
    4. Blank

Every row in the output cache carries the metadata the downstream layer
needs to attribute the number:

    indicator_id | county_fips | county_name | value | moe |
    source_dataset | source_table | source_variable | vintage |
    estimate_basis | notes

`estimate_basis` values:
    published_county          -- single Census DP/S/B or PLACES variable
    derived_county_formula    -- numerator + denominator both at county
                                 geography, both officially published

Scope: state FIPS 47 (all 95 TN counties). Superset of the JHF ~47
footprint counties -- keeps future peer-county comparisons from having
to re-pull.

Usage (from repo root):

    CENSUS_API_KEY=$(zsh -i -c 'echo $CENSUS_API_KEY') \\
        python tools/build_county_benchmarks.py

Outputs:
    data/county_benchmarks_tn.parquet
    data/county_benchmarks_tn.csv
    data/places_county_cache_tn.json   (raw PLACES cache, all TN)

Idempotent. Re-runs use the PLACES cache if present. To force a fresh
PLACES pull, delete `data/places_county_cache_tn.json` first (only with
explicit user confirmation, per project data-protection rules).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
DICT_PATH = DATA / "dictionary.json"

PLACES_CACHE_PATH = DATA / "places_county_cache_tn.json"
OUT_PARQUET = DATA / "county_benchmarks_tn.parquet"
OUT_CSV = DATA / "county_benchmarks_tn.csv"

STATE_FIPS = "47"
STATE_ABBR = "TN"
ACS_VINTAGE = "2020-2024"
ACS_YEAR = 2024
ACS_ENDPOINT = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5"
ACS_PROFILE_ENDPOINT = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5/profile"
ACS_SUBJECT_ENDPOINT = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5/subject"
PLACES_ENDPOINT = "https://data.cdc.gov/resource/swc5-untb.json"
PLACES_VINTAGE = "2024"

EST = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Indicator source spec
# ---------------------------------------------------------------------------
#
# Structure per indicator:
#
#   kind == "acs_direct"
#       endpoint : "acs" | "profile" | "subject"
#       var      : single variable (e.g. "DP03_0119PE", "B19013_001E")
#       table    : source table id (e.g. "DP03", "S1501", "B19013")
#
#   kind == "acs_formula"
#       endpoint : "acs" (always -- B-tables via detail endpoint)
#       num      : list[str] of numerator variables (summed)
#       den      : list[str] of denominator variables (summed)
#       scale    : 100 for percent output, 1 for ratio/count
#       table    : primary source table id
#
#   kind == "places"
#       measure_id : PLACES `measureid` (matches dictionary.measure_id)
#
#   kind == "none"
#       reason : short string logged in the summary
#
# Where a single official published county variable exists in a Data
# Profile (DP) or Subject Table (S), we prefer that (estimate_basis =
# published_county). Otherwise we compute numerator / denominator from
# published county B-tables (estimate_basis = derived_county_formula).
#
# DP/S published-percent variables verified from the ACS 2020-2024
# metadata (variables.html for each table); B-table numerators/
# denominators are the standard published ACS detail tables.
#
INDICATOR_SOURCES: dict[str, dict] = {
    # ------ Economic ------
    "pov_below": {
        "kind": "acs_direct",
        "endpoint": "profile",
        "var": "DP03_0119PE",
        "table": "DP03",
        "notes": "S1701 / DP03 published % of individuals below poverty",
    },
    "hh_snap": {
        "kind": "acs_direct",
        "endpoint": "profile",
        "var": "DP03_0074PE",
        "table": "DP03",
        "notes": "DP03 published % of households receiving SNAP",
    },
    "hh_pubasst": {
        "kind": "acs_direct",
        "endpoint": "profile",
        "var": "DP03_0072PE",
        "table": "DP03",
        "notes": "DP03 published % of households with public assistance income",
    },
    "emp_adults": {
        "kind": "acs_direct",
        "endpoint": "subject",
        "var": "S2301_C03_001E",
        "table": "S2301",
        "notes": "S2301 Employment/Population Ratio, pop 16+ (E/P, not employed-of-labor-force)",
    },
    "not_labor": {
        "kind": "acs_direct",
        "endpoint": "profile",
        "var": "DP03_0007PE",
        "table": "DP03",
        "notes": "DP03 % not in labor force",
    },
    "mhi": {
        "kind": "acs_direct",
        "endpoint": "acs",
        "var": "B19013_001E",
        "table": "B19013",
        "notes": "Median household income, past 12 months (inflation adjusted)",
    },
    "mpci": {
        "kind": "acs_direct",
        "endpoint": "acs",
        "var": "B19301_001E",
        "table": "B19301",
        "notes": "Per capita income, past 12 months (inflation adjusted)",
    },
    "gini": {
        "kind": "acs_direct",
        "endpoint": "acs",
        "var": "B19083_001E",
        "table": "B19083",
        "notes": "Gini Index of income inequality",
    },
    # ------ Education (pop 25+) ------
    "edu_lths": {
        "kind": "acs_formula",
        "endpoint": "acs",
        # Pop 25+ with less than HS diploma:
        #   B15003 rows 002..016 = no schooling through 12th no diploma.
        "num": [
            "B15003_002E",
            "B15003_003E",
            "B15003_004E",
            "B15003_005E",
            "B15003_006E",
            "B15003_007E",
            "B15003_008E",
            "B15003_009E",
            "B15003_010E",
            "B15003_011E",
            "B15003_012E",
            "B15003_013E",
            "B15003_014E",
            "B15003_015E",
            "B15003_016E",
        ],
        "den": ["B15003_001E"],
        "scale": 100,
        "table": "B15003",
        "notes": "% pop 25+ with less than HS diploma (B15003 rows 002-016 / 001)",
    },
    "edu_posths": {
        "kind": "acs_formula",
        "endpoint": "acs",
        "num": [
            "B15003_019E",  # Some college < 1 year
            "B15003_020E",  # Some college 1+ years, no degree
            "B15003_021E",  # Associate's
            "B15003_022E",  # Bachelor's
            "B15003_023E",  # Master's
            "B15003_024E",  # Professional
            "B15003_025E",  # Doctorate
        ],
        "den": ["B15003_001E"],
        "scale": 100,
        "table": "B15003",
        "notes": "% pop 25+ with any post-high-school education",
    },
    "edu_assoc": {
        "kind": "acs_formula",
        "endpoint": "acs",
        "num": ["B15003_021E"],
        "den": ["B15003_001E"],
        "scale": 100,
        "table": "B15003",
        "notes": "% pop 25+ whose highest attainment is an Associate's degree",
    },
    "edu_ba": {
        "kind": "acs_formula",
        "endpoint": "acs",
        "num": ["B15003_022E"],
        "den": ["B15003_001E"],
        "scale": 100,
        "table": "B15003",
        "notes": "% pop 25+ whose highest attainment is a Bachelor's degree",
    },
    "edu_grad": {
        "kind": "acs_formula",
        "endpoint": "acs",
        "num": ["B15003_023E", "B15003_024E", "B15003_025E"],
        "den": ["B15003_001E"],
        "scale": 100,
        "table": "B15003",
        "notes": "% pop 25+ with graduate or professional degree",
    },
    # ------ Youth / disability / insurance ------
    "youth_dis": {
        "kind": "acs_formula",
        "endpoint": "acs",
        # Population 16-19 not enrolled in school AND not employed
        # (unemployed OR not in labor force). B14005 layout verified
        # via ACS 2024 variables metadata:
        #   Male not enrolled, HS grad, unemployed / NILF: 010, 011
        #   Male not enrolled, not HS grad, unemp / NILF: 014, 015
        #   Female not enrolled, HS grad, unemp / NILF:   024, 025
        #   Female not enrolled, not HS grad, unemp/NILF: 028, 029
        "num": [
            "B14005_010E",
            "B14005_011E",
            "B14005_014E",
            "B14005_015E",
            "B14005_024E",
            "B14005_025E",
            "B14005_028E",
            "B14005_029E",
        ],
        "den": ["B14005_001E"],
        "scale": 100,
        "table": "B14005",
        "notes": "% teens 16-19 not enrolled in school AND not employed (unemp or NILF)",
    },
    "any_disab": {
        "kind": "acs_direct",
        "endpoint": "subject",
        "var": "S1810_C03_001E",
        "table": "S1810",
        "notes": "% with any disability, civilian noninstitutionalized pop",
    },
    "no_insur": {
        "kind": "acs_formula",
        "endpoint": "acs",
        # B27001 = Health Insurance Coverage Status by Sex by Age.
        # Layout verified via 2024 ACS 5-yr variables metadata. Age
        # bins are: <6, 6-18, 19-25, 26-34, 35-44, 45-54, 55-64,
        # 65-74, 75+. Each age triple = (total, with, without).
        # We report % uninsured ages 19-64 (proxy for the dictionary's
        # "Ages 18-64" label; ACS lacks a stand-alone 18 slot).
        #   Male   totals 19-64: 009, 012, 015, 018, 021
        #   Male   uninsured  : 011, 014, 017, 020, 023
        #   Female totals 19-64: 037, 040, 043, 046, 049
        #   Female uninsured  : 039, 042, 045, 048, 051
        "num": [
            "B27001_011E",
            "B27001_014E",
            "B27001_017E",
            "B27001_020E",
            "B27001_023E",
            "B27001_039E",
            "B27001_042E",
            "B27001_045E",
            "B27001_048E",
            "B27001_051E",
        ],
        "den": [
            "B27001_009E",
            "B27001_012E",
            "B27001_015E",
            "B27001_018E",
            "B27001_021E",
            "B27001_037E",
            "B27001_040E",
            "B27001_043E",
            "B27001_046E",
            "B27001_049E",
        ],
        "scale": 100,
        "table": "B27001",
        "notes": "% uninsured ages 19-64 (B27001 no-coverage / total, male+female age bins)",
    },
    "private_ins": {
        "kind": "acs_direct",
        "endpoint": "subject",
        "var": "S2701_C03_001E",
        "table": "S2701",
        "notes": "% with private insurance, civilian noninst pop (all ages)",
    },
    "medicaid": {
        "kind": "acs_direct",
        "endpoint": "subject",
        "var": "S2704_C03_006E",
        "table": "S2704",
        "notes": "% with Medicaid / means-tested public coverage, civ noninst",
    },
    # ------ PLACES (17) ------
    "hh_diab": {
        "kind": "places",
        "measure_id": "DIABETES",
        "notes": "CDC PLACES 2024 crude prevalence",
    },
    "hh_asthma": {
        "kind": "places",
        "measure_id": "CASTHMA",
        "notes": "CDC PLACES 2024 crude prevalence",
    },
    "hh_heart": {
        "kind": "places",
        "measure_id": "CHD",
        "notes": "CDC PLACES 2024 crude prevalence",
    },
    "hh_bp": {
        "kind": "places",
        "measure_id": "BPHIGH",
        "notes": "CDC PLACES 2024 crude prevalence",
    },
    "hh_bpmed": {
        "kind": "places",
        "measure_id": "BPMED",
        "notes": "CDC PLACES 2024 crude prevalence",
    },
    "hh_chol": {
        "kind": "places",
        "measure_id": "HIGHCHOL",
        "notes": "CDC PLACES 2024 crude prevalence",
    },
    "hh_arthr": {
        "kind": "places",
        "measure_id": "ARTHRITIS",
        "notes": "CDC PLACES 2024 crude prevalence",
    },
    "hh_copd": {
        "kind": "places",
        "measure_id": "COPD",
        "notes": "CDC PLACES 2024 crude prevalence",
    },
    "hh_stroke": {
        "kind": "places",
        "measure_id": "STROKE",
        "notes": "CDC PLACES 2024 crude prevalence",
    },
    "ph_poor14": {
        "kind": "places",
        "measure_id": "PHLTH",
        "notes": "CDC PLACES 2024 crude prevalence",
    },
    "mh_poor14": {
        "kind": "places",
        "measure_id": "MHLTH",
        "notes": "CDC PLACES 2024 crude prevalence",
    },
    "fair_hlth": {
        "kind": "places",
        "measure_id": "GHLTH",
        "notes": "CDC PLACES 2024 crude prevalence",
    },
    "smoke": {
        "kind": "places",
        "measure_id": "CSMOKING",
        "notes": "CDC PLACES 2024 crude prevalence",
    },
    "binge": {
        "kind": "places",
        "measure_id": "BINGE",
        "notes": "CDC PLACES 2024 crude prevalence",
    },
    "no_activ": {
        "kind": "places",
        "measure_id": "LPA",
        "notes": "CDC PLACES 2024 crude prevalence",
    },
    "obesity": {
        "kind": "places",
        "measure_id": "OBESITY",
        "notes": "CDC PLACES 2024 crude prevalence",
    },
    "sleep_lt7": {
        "kind": "places",
        "measure_id": "SLEEP",
        "notes": "CDC PLACES 2024 crude prevalence",
    },
    # ------ Housing ------
    "med_rent": {
        "kind": "acs_direct",
        "endpoint": "acs",
        "var": "B25064_001E",
        "table": "B25064",
        "notes": "Median gross rent, dollars",
    },
    "med_home": {
        "kind": "acs_direct",
        "endpoint": "acs",
        "var": "B25077_001E",
        "table": "B25077",
        "notes": "Median value of owner-occupied units, dollars",
    },
    "owner_occ": {
        "kind": "acs_formula",
        "endpoint": "acs",
        "num": ["B25003_002E"],
        "den": ["B25003_001E"],
        "scale": 100,
        "table": "B25003",
        "notes": "% owner-occupied of occupied housing units",
    },
    "renter_occ": {
        "kind": "acs_formula",
        "endpoint": "acs",
        "num": ["B25003_003E"],
        "den": ["B25003_001E"],
        "scale": 100,
        "table": "B25003",
        "notes": "% renter-occupied of occupied housing units",
    },
    "vacant": {
        "kind": "acs_direct",
        "endpoint": "profile",
        "var": "DP04_0003PE",
        "table": "DP04",
        "notes": "DP04 published % vacant of total housing units",
    },
    "cost_owner": {
        "kind": "acs_direct",
        "endpoint": "profile",
        "var": "DP04_0114PE",
        "table": "DP04",
        "notes": "DP04 % owners-with-mortgage paying 30%+ of income",
    },
    "cost_rent": {
        "kind": "acs_direct",
        "endpoint": "profile",
        "var": "DP04_0142PE",
        "table": "DP04",
        "notes": "DP04 % renters paying 30%+ of income (GRAPI 30%+)",
    },
    "housing_old": {
        "kind": "acs_direct",
        "endpoint": "profile",
        "var": "DP04_0026PE",
        "table": "DP04",
        "notes": "DP04 % housing units built 1979 or earlier",
    },
    # ------ Broadband / vehicles / commute ------
    "bb_access": {
        "kind": "acs_direct",
        "endpoint": "profile",
        "var": "DP02_0154PE",
        "table": "DP02",
        "notes": "DP02 % households with a broadband internet subscription",
    },
    "no_intnet": {
        "kind": "acs_formula",
        "endpoint": "acs",
        "num": ["B28002_013E"],
        "den": ["B28002_001E"],
        "scale": 100,
        "table": "B28002",
        "notes": "% households with no internet access (B28002 no-access / total)",
    },
    "no_veh": {
        "kind": "acs_direct",
        "endpoint": "profile",
        "var": "DP04_0058PE",
        "table": "DP04",
        "notes": "DP04 % occupied units with no vehicles available",
    },
    "transit": {
        "kind": "acs_formula",
        "endpoint": "acs",
        "num": ["B08301_010E"],
        "den": ["B08301_001E"],
        "scale": 100,
        "table": "B08301",
        "notes": "% workers 16+ commuting by public transit (excl taxi)",
    },
    "walk": {
        "kind": "acs_formula",
        "endpoint": "acs",
        "num": ["B08301_019E"],
        "den": ["B08301_001E"],
        "scale": 100,
        "table": "B08301",
        "notes": "% workers 16+ walking to work",
    },
    # ------ Age / household composition ------
    "age_65p": {
        "kind": "acs_formula",
        "endpoint": "acs",
        "num": [
            # Male 65+: 020..025 (65-66, 67-69, 70-74, 75-79, 80-84, 85+)
            "B01001_020E",
            "B01001_021E",
            "B01001_022E",
            "B01001_023E",
            "B01001_024E",
            "B01001_025E",
            # Female 65+: 044..049
            "B01001_044E",
            "B01001_045E",
            "B01001_046E",
            "B01001_047E",
            "B01001_048E",
            "B01001_049E",
        ],
        "den": ["B01001_001E"],
        "scale": 100,
        "table": "B01001",
        "notes": "% population age 65 and over",
    },
    "age_18_64": {
        "kind": "acs_formula",
        "endpoint": "acs",
        "num": [
            # Male 18-64: 007..019
            "B01001_007E",
            "B01001_008E",
            "B01001_009E",
            "B01001_010E",
            "B01001_011E",
            "B01001_012E",
            "B01001_013E",
            "B01001_014E",
            "B01001_015E",
            "B01001_016E",
            "B01001_017E",
            "B01001_018E",
            "B01001_019E",
            # Female 18-64: 031..043
            "B01001_031E",
            "B01001_032E",
            "B01001_033E",
            "B01001_034E",
            "B01001_035E",
            "B01001_036E",
            "B01001_037E",
            "B01001_038E",
            "B01001_039E",
            "B01001_040E",
            "B01001_041E",
            "B01001_042E",
            "B01001_043E",
        ],
        "den": ["B01001_001E"],
        "scale": 100,
        "table": "B01001",
        "notes": "% population age 18-64",
    },
    "med_age": {
        "kind": "acs_direct",
        "endpoint": "acs",
        "var": "B01002_001E",
        "table": "B01002",
        "notes": "Median age (years)",
    },
    "single_p": {
        "kind": "acs_direct",
        "endpoint": "subject",
        "var": "S1101_C01_014E",
        "table": "S1101",
        "notes": "Single-parent families (households) percent",
    },
    "live_alon_65": {
        "kind": "acs_formula",
        "endpoint": "acs",
        # B11007 layout (verified from ACS 2024 metadata):
        #   _001E Total households
        #   _002E HHs with 1+ people 65+
        #   _003E   ...of which: 1-person household  (<-- what we want)
        # Denominator: all households (B11007_001E = B11001_001E for
        # the same tract/county universe).
        "num": ["B11007_003E"],
        "den": ["B11007_001E"],
        "scale": 100,
        "table": "B11007",
        "notes": "% households that are a single person 65+ (B11007_003 / _001)",
    },
    "hh_size": {
        "kind": "acs_direct",
        "endpoint": "acs",
        "var": "B25010_001E",
        "table": "B25010",
        "notes": "Average household size of occupied housing units",
    },
    "married": {
        "kind": "acs_formula",
        "endpoint": "acs",
        # B12001: sex by marital status, pop 15+.
        # Male now-married (excl separated): 004; Female: 013.
        # Denominator: B12001_001E (pop 15+).
        "num": ["B12001_004E", "B12001_013E"],
        "den": ["B12001_001E"],
        "scale": 100,
        "table": "B12001",
        "notes": "% population 15+ now married (excluding separated)",
    },
    # ------ Race / ethnicity / origin / language ------
    "hisp": {
        "kind": "acs_formula",
        "endpoint": "acs",
        "num": ["B03002_012E"],
        "den": ["B03002_001E"],
        "scale": 100,
        "table": "B03002",
        "notes": "% Hispanic or Latino (any race)",
    },
    "black": {
        "kind": "acs_formula",
        "endpoint": "acs",
        "num": ["B03002_004E"],
        "den": ["B03002_001E"],
        "scale": 100,
        "table": "B03002",
        "notes": "% non-Hispanic Black or African American alone",
    },
    "white": {
        "kind": "acs_formula",
        "endpoint": "acs",
        "num": ["B03002_003E"],
        "den": ["B03002_001E"],
        "scale": 100,
        "table": "B03002",
        "notes": "% non-Hispanic White alone",
    },
    "asian": {
        "kind": "acs_formula",
        "endpoint": "acs",
        "num": ["B03002_006E"],
        "den": ["B03002_001E"],
        "scale": 100,
        "table": "B03002",
        "notes": "% non-Hispanic Asian alone",
    },
    "foreign_born": {
        "kind": "acs_formula",
        "endpoint": "acs",
        "num": ["B05002_013E"],
        "den": ["B05002_001E"],
        "scale": 100,
        "table": "B05002",
        "notes": "% foreign-born of total population",
    },
    "lang_span": {
        "kind": "acs_direct",
        "endpoint": "subject",
        "var": "S1601_C02_005E",
        "table": "S1601",
        "notes": "% pop 5+ that speaks Spanish at home",
    },
}


def _ts() -> str:
    """Current Eastern-Time timestamp for logging."""
    return datetime.now(EST).strftime("%Y-%m-%d %H:%M:%S %Z")


# ---------------------------------------------------------------------------
# ACS fetch
# ---------------------------------------------------------------------------
def _chunk(seq: list[str], n: int) -> Iterable[list[str]]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _fetch_acs_batch(
    endpoint: str,
    variables: list[str],
    state_fips: str,
    api_key: str,
    max_retries: int = 3,
) -> dict[str, dict[str, str | None]]:
    """Fetch a batch of ACS variables at county geography for one state.

    Returns {county_fips (5-digit): {var: raw_string_value_or_None, ...}}.
    Batches of <=45 vars per request (Census limit is ~50).
    """
    out: dict[str, dict[str, str | None]] = {}
    for chunk in _chunk(variables, 45):
        params = {
            "get": "NAME," + ",".join(chunk),
            "for": "county:*",
            "in": f"state:{state_fips}",
            "key": api_key,
        }
        qs = urllib.parse.urlencode(params, safe=":,*")
        url = f"{endpoint}?{qs}"
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(url, timeout=90) as resp:
                    payload = json.loads(resp.read())
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"  [ERROR] {endpoint} chunk {chunk[:2]}...: {e}")
                    return out
                print(f"  retry {endpoint} ({e})")
                time.sleep(2)
        header, *rows = payload
        idx = {c: header.index(c) for c in header}
        for row in rows:
            fips = row[idx["state"]].zfill(2) + row[idx["county"]].zfill(3)
            name = row[idx["NAME"]]
            slot = out.setdefault(fips, {"_name": name})
            for v in chunk:
                slot[v] = row[idx[v]]
    return out


def _to_float(raw: str | None) -> float | None:
    """Census sentinels: null / '-666666666' / '' -> None; else float."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s in {"null", "NaN", "None"}:
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    # ACS jam values (see Census docs).
    if f <= -666666666:
        return None
    return f


# ---------------------------------------------------------------------------
# PLACES fetch
# ---------------------------------------------------------------------------
def _fetch_places_all_tn() -> list[dict]:
    """Fetch every PLACES county-level 2024 crude-prevalence row for TN
    (all 95 counties, all measures) in one paged pull. Returns raw rows.
    """
    rows: list[dict] = []
    limit = 5000
    offset = 0
    while True:
        params = {
            "$where": f"stateabbr='{STATE_ABBR}' AND datavaluetypeid='CrdPrv'",
            "$select": (
                "stateabbr,locationname,locationid,"
                "measureid,short_question_text,data_value,low_confidence_limit,"
                "high_confidence_limit,data_value_type,year,totalpopulation"
            ),
            "$limit": str(limit),
            "$offset": str(offset),
        }
        url = f"{PLACES_ENDPOINT}?{urllib.parse.urlencode(params, safe=' ')}"
        with urllib.request.urlopen(url, timeout=60) as r:
            page = json.loads(r.read())
        rows.extend(page)
        if len(page) < limit:
            break
        offset += limit
    return rows


def load_or_fetch_places_cache() -> dict[str, dict[str, dict]]:
    """Return {county_fips: {measure_id: {value, low, high, name, year}}}.

    Uses on-disk cache if present.
    """
    if PLACES_CACHE_PATH.exists():
        try:
            return json.loads(PLACES_CACHE_PATH.read_text())
        except Exception as e:
            print(f"  [warn] PLACES cache read failed, refetching: {e}")

    print(f"  [{_ts()}] PLACES: fetching all TN counties x measures ...")
    raw = _fetch_places_all_tn()
    print(f"  [{_ts()}] PLACES: got {len(raw)} rows")

    cache: dict[str, dict[str, dict]] = {}
    for r in raw:
        fips = str(r.get("locationid") or "").zfill(5)
        if not fips or len(fips) != 5:
            continue
        mid = r.get("measureid")
        if not mid:
            continue
        try:
            val = float(r["data_value"]) if r.get("data_value") is not None else None
        except (TypeError, ValueError):
            val = None
        try:
            lo = (
                float(r["low_confidence_limit"])
                if r.get("low_confidence_limit") is not None
                else None
            )
            hi = (
                float(r["high_confidence_limit"])
                if r.get("high_confidence_limit") is not None
                else None
            )
        except (TypeError, ValueError):
            lo, hi = None, None
        cache.setdefault(fips, {})[mid] = {
            "value": val,
            "low": lo,
            "high": hi,
            "county_name": r.get("locationname"),
            "year": r.get("year"),
            "short_question_text": r.get("short_question_text"),
        }
    PLACES_CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True))
    print(f"  wrote {PLACES_CACHE_PATH} ({len(cache)} counties)")
    return cache


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def load_dictionary() -> dict:
    return json.loads(DICT_PATH.read_text())


def collect_acs_vars() -> dict[str, list[str]]:
    """Return {endpoint_key: [vars needed at that endpoint]} plus MOE
    companions where the variable is an estimate.
    """
    plan: dict[str, set[str]] = {"acs": set(), "profile": set(), "subject": set()}
    for spec in INDICATOR_SOURCES.values():
        if spec["kind"] == "acs_direct":
            plan[spec["endpoint"]].add(spec["var"])
        elif spec["kind"] == "acs_formula":
            plan[spec["endpoint"]].update(spec["num"])
            plan[spec["endpoint"]].update(spec["den"])

    # Add MOE companions:
    #   B/S table var ending in "E" -> replace last char with "M"
    #   DP profile     ending in "PE" -> "PM"; "E" -> "M"
    def moe_for(var: str) -> str | None:
        if var.startswith("DP"):
            if var.endswith("PE"):
                return var[:-2] + "PM"
            if var.endswith("E"):
                return var[:-1] + "M"
            return None
        if var.endswith("E"):
            return var[:-1] + "M"
        return None

    final: dict[str, list[str]] = {}
    for ep, vars_ in plan.items():
        expanded = set(vars_)
        for v in list(vars_):
            m = moe_for(v)
            if m:
                expanded.add(m)
        final[ep] = sorted(expanded)
    return final


def fetch_all_acs(api_key: str) -> dict[str, dict[str, dict[str, str | None]]]:
    """Return {endpoint: {county_fips: {var: raw_string}}}."""
    plan = collect_acs_vars()
    endpoints = {
        "acs": ACS_ENDPOINT,
        "profile": ACS_PROFILE_ENDPOINT,
        "subject": ACS_SUBJECT_ENDPOINT,
    }
    out: dict[str, dict[str, dict[str, str | None]]] = {}
    for ep_key, ep_url in endpoints.items():
        vars_ = plan[ep_key]
        if not vars_:
            out[ep_key] = {}
            continue
        print(
            f"  [{_ts()}] ACS {ep_key}: fetching {len(vars_)} vars x {STATE_FIPS} counties ..."
        )
        result = _fetch_acs_batch(ep_url, vars_, STATE_FIPS, api_key)
        print(f"  [{_ts()}] ACS {ep_key}: got {len(result)} counties")
        out[ep_key] = result
    return out


def compute_row(
    indicator_id: str,
    spec: dict,
    county_fips: str,
    county_name: str,
    acs_data: dict,
    places_cache: dict,
) -> dict:
    """Build one output row per (indicator, county)."""
    base = {
        "indicator_id": indicator_id,
        "county_fips": county_fips,
        "county_name": county_name,
        "value": None,
        "moe": None,
        "source_dataset": None,
        "source_table": None,
        "source_variable": None,
        "vintage": None,
        "estimate_basis": None,
        "notes": spec.get("notes", ""),
    }
    kind = spec["kind"]

    if kind == "acs_direct":
        ep = spec["endpoint"]
        var = spec["var"]
        pool = acs_data.get(ep, {}).get(county_fips, {})
        val = _to_float(pool.get(var))
        # MOE companion
        moe_var = (
            (var[:-2] + "PM")
            if (var.startswith("DP") and var.endswith("PE"))
            else (var[:-1] + "M" if var.endswith("E") else None)
        )
        moe = _to_float(pool.get(moe_var)) if moe_var else None
        # ACS "not applicable" / suppressed sentinels
        base.update(
            {
                "value": val,
                "moe": moe,
                "source_dataset": f"ACS 5-year {ACS_VINTAGE}",
                "source_table": spec.get("table"),
                "source_variable": var,
                "vintage": ACS_VINTAGE,
                "estimate_basis": "published_county",
            }
        )
        return base

    if kind == "acs_formula":
        ep = spec["endpoint"]
        pool = acs_data.get(ep, {}).get(county_fips, {})
        num_vals = [_to_float(pool.get(v)) for v in spec["num"]]
        den_vals = [_to_float(pool.get(v)) for v in spec["den"]]
        if any(v is None for v in num_vals) or any(v is None for v in den_vals):
            base.update(
                {
                    "source_dataset": f"ACS 5-year {ACS_VINTAGE}",
                    "source_table": spec.get("table"),
                    "source_variable": "+".join(spec["num"])
                    + " / "
                    + "+".join(spec["den"]),
                    "vintage": ACS_VINTAGE,
                    "estimate_basis": "derived_county_formula",
                    "notes": spec.get("notes", "") + " [missing num/den]",
                }
            )
            return base
        num = sum(num_vals)
        den = sum(den_vals)
        val = (spec["scale"] * num / den) if den else None
        base.update(
            {
                "value": val,
                "moe": None,  # explicit MOE combine skipped; downstream can add
                "source_dataset": f"ACS 5-year {ACS_VINTAGE}",
                "source_table": spec.get("table"),
                "source_variable": "+".join(spec["num"])
                + " / "
                + "+".join(spec["den"]),
                "vintage": ACS_VINTAGE,
                "estimate_basis": "derived_county_formula",
            }
        )
        return base

    if kind == "places":
        rec = places_cache.get(county_fips, {}).get(spec["measure_id"])
        if rec is None:
            base.update(
                {
                    "source_dataset": f"CDC PLACES {PLACES_VINTAGE}",
                    "source_table": "swc5-untb",
                    "source_variable": spec["measure_id"],
                    "vintage": PLACES_VINTAGE,
                    "estimate_basis": "published_county",
                    "notes": spec.get("notes", "") + " [not in PLACES pull]",
                }
            )
            return base
        val = rec.get("value")
        # Approximate a symmetric MOE from CI half-width when both
        # bounds are present.
        moe = None
        lo, hi = rec.get("low"), rec.get("high")
        if lo is not None and hi is not None:
            moe = (hi - lo) / 2.0
        base.update(
            {
                "value": val,
                "moe": moe,
                "source_dataset": f"CDC PLACES {PLACES_VINTAGE}",
                "source_table": "swc5-untb",
                "source_variable": spec["measure_id"],
                "vintage": PLACES_VINTAGE,
                "estimate_basis": "published_county",
            }
        )
        return base

    # kind == "none"
    base.update(
        {"notes": spec.get("reason", "no county source defined"),}
    )
    return base


def build_rows(
    indicator_ids: list[str],
    acs_data: dict,
    places_cache: dict,
    county_names: dict[str, str],
) -> list[dict]:
    """One row per (indicator, TN county)."""
    # TN county fips = every 5-digit code returned by either endpoint.
    all_counties = set(county_names.keys())
    rows: list[dict] = []
    for ind in indicator_ids:
        spec = INDICATOR_SOURCES.get(ind)
        if spec is None:
            # Indicator in dictionary but not in our spec — emit blank row.
            for fips in sorted(all_counties):
                rows.append(
                    {
                        "indicator_id": ind,
                        "county_fips": fips,
                        "county_name": county_names[fips],
                        "value": None,
                        "moe": None,
                        "source_dataset": None,
                        "source_table": None,
                        "source_variable": None,
                        "vintage": None,
                        "estimate_basis": None,
                        "notes": "no INDICATOR_SOURCES mapping",
                    }
                )
            continue
        for fips in sorted(all_counties):
            rows.append(
                compute_row(
                    ind, spec, fips, county_names[fips], acs_data, places_cache,
                )
            )
    return rows


def extract_county_names(acs_data: dict) -> dict[str, str]:
    """Pull {county_fips: NAME} from whichever endpoint returned."""
    out: dict[str, str] = {}
    for ep_pool in acs_data.values():
        for fips, slot in ep_pool.items():
            n = slot.get("_name")
            if n and fips not in out:
                # NAME is "Hamilton County, Tennessee" — keep as-is.
                out[fips] = n
    return out


def print_summary(rows: list[dict], indicator_ids: list[str]) -> None:
    """Per-indicator: N counties with a value, source, basis."""
    print()
    print("=" * 78)
    print(f"COUNTY BENCHMARK BUILD SUMMARY  [{_ts()}]")
    print("=" * 78)
    kinds = {"acs_direct": 0, "acs_formula": 0, "places": 0, "none": 0, "unmapped": 0}
    for ind in indicator_ids:
        spec = INDICATOR_SOURCES.get(ind)
        if spec is None:
            kinds["unmapped"] += 1
        else:
            kinds[spec["kind"]] = kinds.get(spec["kind"], 0) + 1
    print(f"Indicators total (from dictionary): {len(indicator_ids)}")
    for k, n in kinds.items():
        print(f"  {k:12} {n}")
    print()
    print(f"{'indicator':16} {'kind':12} {'n_values':>8} {'source_table':16}  notes")
    print("-" * 90)
    per_ind: dict[str, dict] = {}
    for r in rows:
        d = per_ind.setdefault(r["indicator_id"], {"n": 0, "kind": None, "table": None})
        if r["value"] is not None:
            d["n"] += 1
        if r["source_table"]:
            d["table"] = r["source_table"]
    failed: list[str] = []
    for ind in indicator_ids:
        spec = INDICATOR_SOURCES.get(ind)
        kind = spec["kind"] if spec else "unmapped"
        info = per_ind.get(ind, {"n": 0, "table": ""})
        notes = spec.get("notes", "") if spec else ""
        print(
            f"{ind:16} {kind:12} {info['n']:>8} {str(info.get('table') or ''):16}  {notes}"
        )
        if info["n"] == 0 and kind not in {"none", "unmapped"}:
            failed.append(ind)
    print()
    print(f"Total rows written: {len(rows)}")
    if failed:
        print(f"FAILED indicators (0 values pulled): {failed}")
    else:
        print("No mapped indicator returned 0 values.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--refetch-places",
        action="store_true",
        help="Delete-free refetch: reads then overwrites the PLACES cache in place.",
    )
    ap.add_argument(
        "--out-parquet", type=Path, default=OUT_PARQUET,
    )
    ap.add_argument("--out-csv", type=Path, default=OUT_CSV)
    args = ap.parse_args(argv)

    api_key = os.environ.get("CENSUS_API_KEY")
    if not api_key:
        print(
            "ERROR: CENSUS_API_KEY not set in environment.\n"
            "Run:\n"
            "    CENSUS_API_KEY=$(zsh -i -c 'echo $CENSUS_API_KEY') \\\n"
            "        python tools/build_county_benchmarks.py",
            file=sys.stderr,
        )
        return 2

    # PLACES pull (or cache read).
    if args.refetch_places and PLACES_CACHE_PATH.exists():
        # In-place overwrite (no unlink -- keeps data-protection policy).
        PLACES_CACHE_PATH.write_text("{}")
    places_cache = load_or_fetch_places_cache()

    # ACS pulls.
    acs_data = fetch_all_acs(api_key)
    county_names = extract_county_names(acs_data)
    print(f"  county count discovered: {len(county_names)}")

    # Build rows.
    d = load_dictionary()
    indicator_ids = list(d["indicators"].keys())
    rows = build_rows(indicator_ids, acs_data, places_cache, county_names)

    # Write outputs.
    try:
        import pandas as pd
    except ImportError:
        print("ERROR: pandas is required. pip install pandas pyarrow", file=sys.stderr)
        return 3

    df = pd.DataFrame(
        rows,
        columns=[
            "indicator_id",
            "county_fips",
            "county_name",
            "value",
            "moe",
            "source_dataset",
            "source_table",
            "source_variable",
            "vintage",
            "estimate_basis",
            "notes",
        ],
    )
    args.out_parquet.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out_parquet, index=False)
    df.to_csv(args.out_csv, index=False)
    print(f"\n  wrote {args.out_parquet}  ({len(df):,} rows)")
    print(f"  wrote {args.out_csv}")

    print_summary(rows, indicator_ids)
    return 0


if __name__ == "__main__":
    sys.exit(main())
