"""Pull ACS 5-year universe (denominator) variables per tract for the
JHFRC pilot region, evaluate each indicator's universe recipe, and
cache the result as data/acs_universes.parquet.

Task #123. Downstream:
    build_rollout_dataset.py joins the parquet on tract_geoid ×
    indicator_id and adds a `universe` column to each rollout row.
    build_arcgis_layer.py pivots that into <indicator>_univ so
    Compare Counties can do universe-weighted aggregation when the
    published <CountyValue> is missing.

Reads:
    data/dictionary.json  (universe recipes from _meta.universe_recipes
                           and per-indicator .universe blocks)
    env CENSUS_API_KEY   (required)

Writes:
    data/acs_universes.parquet with columns:
        tract_geoid   str (11-char FIPS)
        vintage       str  ('2020-2024' currently)
        indicator_id  str  ('pov_below', 'edu_ba', ...)
        universe      float64  (evaluated formula result per tract)

Formula language (whitelisted subset of Python):
    - Variable names: /^B\\d{5}_\\d{3}[EM]$/  (ACS variable IDs)
    - Operators: + - * / **  (integer / float arithmetic only)
    - Parentheses, integer / float literals
    - No calls, attribute access, comprehensions, or names outside the
      resolved ACS variables. Anything else raises ValueError.

Vintage: currently only 2020-2024 (ACS 5-year 2024 release). To pull
2015-2019 as a comparison window for trend-basis check, pass
--vintage 2015-2019.

Idempotent + cheap: two batched API calls per state (up to 50 vars
each), then in-memory eval.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
DICT_PATH = DATA / "dictionary.json"
OUT_PATH = DATA / "acs_universes.parquet"

PILOT_STATE_FIPS = ["47", "13", "01", "37"]  # TN, GA, AL, NC
DEFAULT_VINTAGE = "2020-2024"
VINTAGE_TO_YEAR = {
    # ACS 5-year releases: the endpoint year is the LATEST year in the
    # 5-year span. 2020-2024 release lives at /2024/acs/acs5.
    "2020-2024": 2024,
    "2015-2019": 2019,
}
ACS_VAR_RE = re.compile(r"^B\d{5}_\d{3}[EM]$")


def load_recipes() -> tuple[dict, dict]:
    """Return (recipes_by_key, indicator_to_recipe) from dictionary.json."""
    with open(DICT_PATH) as f:
        d = json.load(f)
    recipes = d.get("_meta", {}).get("universe_recipes")
    if not recipes:
        raise SystemExit(
            "No universe recipes in dictionary.json._meta.universe_recipes. "
            "Run scripts/patch_universes.py first."
        )
    ind_map: dict[str, dict] = {}
    for ind_id, entry in d.get("indicators", {}).items():
        u = entry.get("universe")
        # Skip legacy string-only universe entries (pre-#123 metadata
        # where .universe was a human-readable label like "Adults 18+"
        # with no formula). Only recipes with a proper acs_vars +
        # formula pair are actionable.
        if isinstance(u, dict) and "formula" in u and "acs_vars" in u:
            ind_map[ind_id] = u
    return recipes, ind_map


def eval_formula(formula: str, values: dict[str, float]) -> float | None:
    """Evaluate an ACS universe formula with the given variable values.

    Only allows +, -, *, /, **, parens, literals, and names matching
    ACS_VAR_RE that are present in `values`. Returns None if any
    referenced variable is missing / None.
    """
    tree = ast.parse(formula, mode="eval")

    def _walk(node):
        if isinstance(node, ast.Expression):
            return _walk(node.body)
        if isinstance(node, ast.BinOp):
            left = _walk(node.left)
            right = _walk(node.right)
            if left is None or right is None:
                return None
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right if right else None
            if isinstance(node.op, ast.Pow):
                return left ** right
            raise ValueError(f"Unsupported operator: {ast.dump(node.op)}")
        if isinstance(node, ast.UnaryOp):
            v = _walk(node.operand)
            if v is None:
                return None
            if isinstance(node.op, ast.USub):
                return -v
            if isinstance(node.op, ast.UAdd):
                return v
            raise ValueError(f"Unsupported unary op: {ast.dump(node.op)}")
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise ValueError(f"Constant type not allowed: {type(node.value)}")
        if isinstance(node, ast.Name):
            if not ACS_VAR_RE.match(node.id):
                raise ValueError(
                    f"Name '{node.id}' does not look like an ACS variable id"
                )
            v = values.get(node.id)
            return None if v is None else float(v)
        raise ValueError(f"Unsupported node: {type(node).__name__}")

    return _walk(tree)


def fetch_state(
    vintage: str,
    state_fips: str,
    variables: list[str],
    api_key: str,
    counties: set[str] | None = None,
) -> list[dict]:
    """Fetch given ACS variables for every tract in a state (optionally
    filtered to a set of 3-digit county codes). Returns list of rows,
    each row = {tract_geoid, ...var: value}.

    ACS caps variables at ~50 per request; batch in chunks.
    """
    year = VINTAGE_TO_YEAR[vintage]
    base = f"https://api.census.gov/data/{year}/acs/acs5"
    all_rows: dict[str, dict] = {}
    CHUNK = 45
    for i in range(0, len(variables), CHUNK):
        chunk = variables[i : i + CHUNK]
        params = {
            "get": ",".join(chunk),
            "for": "tract:*",
            "in": f"state:{state_fips} county:*",
            "key": api_key,
        }
        qs = urllib.parse.urlencode(params, safe=":,*")
        url = f"{base}?{qs}"
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    payload = json.loads(r.read())
                break
            except Exception as e:
                if attempt == 2:
                    raise
                print(f"  retry state={state_fips} chunk#{i//CHUNK} ({e})")
                time.sleep(2)
        header, *rows = payload
        idx = {c: header.index(c) for c in header}
        for row in rows:
            geoid = (
                row[idx["state"]].zfill(2)
                + row[idx["county"]].zfill(3)
                + row[idx["tract"]].zfill(6)
            )
            county_code = row[idx["county"]].zfill(3)
            if counties is not None and county_code not in counties:
                continue
            r = all_rows.setdefault(geoid, {"tract_geoid": geoid})
            for v in chunk:
                cell = row[idx[v]]
                try:
                    r[v] = float(cell) if cell not in (None, "", "null") else None
                except (TypeError, ValueError):
                    r[v] = None
    return list(all_rows.values())


def load_pilot_counties() -> dict[str, set[str]]:
    """Return {state_fips: {3-digit county codes}} for the 47-county
    pilot region. Sourced from the rollout parquet (county_fips = SSCCC)
    if present, else falls back to fetching every tract in each pilot
    state (cheap enough)."""
    import pandas as pd  # deferred so the file imports without pandas

    pq = DATA / "rollout_indicators.parquet"
    if not pq.exists():
        print("  rollout parquet missing — will fetch every tract in each pilot state")
        return {s: None for s in PILOT_STATE_FIPS}  # type: ignore
    df = pd.read_parquet(pq, columns=["county_fips"])
    out: dict[str, set[str]] = {s: set() for s in PILOT_STATE_FIPS}
    for c in df["county_fips"].dropna().unique():
        c = str(c).zfill(5)
        state, county = c[:2], c[2:]
        if state in out:
            out[state].add(county)
    return {k: v for k, v in out.items() if v}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pull ACS universe variables.")
    ap.add_argument(
        "--vintage", default=DEFAULT_VINTAGE, choices=list(VINTAGE_TO_YEAR.keys())
    )
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args(argv)

    api_key = os.environ.get("CENSUS_API_KEY")
    if not api_key:
        raise SystemExit(
            "CENSUS_API_KEY not set. Run: zsh -i -c 'echo $CENSUS_API_KEY' to "
            "verify, or export it before this script."
        )

    recipes, ind_map = load_recipes()
    all_vars = sorted({v for r in recipes.values() for v in r["acs_vars"]})
    print(f"Universe recipes: {len(recipes)}  |  indicators mapped: {len(ind_map)}")
    print(f"Unique ACS variables to fetch: {len(all_vars)}")

    pilot = load_pilot_counties()
    print(f"Pilot states: {list(pilot.keys())}")

    # ---- Pull per state ----
    import pandas as pd

    frames = []
    for state_fips, counties in pilot.items():
        cnt_str = f"({len(counties)} counties)" if counties else "(all counties)"
        print(f"\n[{state_fips}] fetching {len(all_vars)} vars {cnt_str} ...")
        rows = fetch_state(
            args.vintage, state_fips, all_vars, api_key, counties=counties,
        )
        print(f"  got {len(rows)} tracts")
        if not rows:
            continue
        frames.append(pd.DataFrame(rows))
    if not frames:
        raise SystemExit("No ACS data returned from any state.")

    tract_vals = pd.concat(frames, ignore_index=True)
    tract_vals["tract_geoid"] = tract_vals["tract_geoid"].astype(str).str.zfill(11)

    # ---- Evaluate per-indicator universe formulas ----
    print(f"\nEvaluating {len(ind_map)} indicator universe formulas...")
    out_rows = []
    n_missing = 0
    for tract in tract_vals.to_dict(orient="records"):
        geoid = tract["tract_geoid"]
        var_values = {k: v for k, v in tract.items() if k != "tract_geoid"}
        for ind_id, recipe in ind_map.items():
            try:
                u = eval_formula(recipe["formula"], var_values)
            except Exception as e:
                if n_missing < 3:
                    print(f"  eval error {ind_id} @ {geoid}: {e}")
                n_missing += 1
                u = None
            out_rows.append(
                {
                    "tract_geoid": geoid,
                    "vintage": args.vintage,
                    "indicator_id": ind_id,
                    "universe": u,
                }
            )
    out = pd.DataFrame(out_rows)
    print(f"Emitted {len(out):,} (tract x indicator) rows.")
    n_pop = out["universe"].notna().sum()
    print(
        f"Non-null universe values: {n_pop:,} / {len(out):,} "
        f"({100 * n_pop / len(out):.1f}%)"
    )
    if n_missing:
        print(f"WARN: {n_missing} eval errors")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)
    print(f"\nWrote {args.out}  ({args.out.stat().st_size:,} bytes)")

    # Also a small per-indicator coverage summary
    cov = (
        out.groupby("indicator_id")["universe"]
        .agg(n_total="count", n_present=lambda s: s.notna().sum(),)
        .reset_index()
    )
    cov["coverage_pct"] = (100 * cov["n_present"] / cov["n_total"]).round(1)
    print("\nPer-indicator coverage (top 5 lowest):")
    for _, r in cov.sort_values("coverage_pct").head(5).iterrows():
        print(
            f"  {r.indicator_id:14s}  {r.n_present:>4}/{r.n_total} ({r.coverage_pct}%)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
