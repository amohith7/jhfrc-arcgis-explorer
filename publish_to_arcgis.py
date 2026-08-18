"""Publish (or overwrite) the JHFRC tract Feature Layer on ArcGIS Online.

Reads:
    data/jhfrc_tracts.gpkg   (produced by build_arcgis_layer.py)
    OR data/jhfrc_tracts.shp (fallback; ArcGIS Online accepts either)

Behavior:
    - First run: creates a new Hosted Feature Layer titled "JHFRC Tracts".
    - Subsequent runs: finds the existing layer by title + owner and
      OVERWRITES it (preserves the layer's item id + URL + any Dashboard
      that references it).
    - Sharing is left at "private" by default. Change in the AGOL UI
      once you're ready to expose it to a group / org / public.

Auth (auto-detected, first match wins):
    1. ARCGIS_USERNAME + ARCGIS_PASSWORD env vars
    2. ARCGIS_TOKEN env var (rare — AGOL rotates tokens; not preferred)
    3. Interactive OAuth on first run (browser opens; session cached
       under ~/.arcgis/)

Never commit credentials. Never paste them into a script. If you need
service-account credentials rotated, do it in the AGOL admin console.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
DATA_DIR = REPO / "data"

DEFAULT_TITLE = "JHFRC Tracts"
DEFAULT_TAGS = ["JHFRC", "SDoH", "census tract", "community profiles"]
DEFAULT_SNIPPET = (
    "Tract-level Social Determinants of Health indicators for the "
    "JHFRC 47-county service region (TN, GA, AL, NC). Produced by the "
    "JHFRC Community Profiles rollout pipeline."
)


def _pick_upload_path() -> Path:
    """Prefer GeoPackage; fall back to zipped Shapefile."""
    gpkg = DATA_DIR / "jhfrc_tracts.gpkg"
    if gpkg.exists():
        return gpkg
    shp = DATA_DIR / "jhfrc_tracts.shp"
    if shp.exists():
        # AGOL expects a zipped Shapefile bundle.
        import zipfile

        zip_path = DATA_DIR / "jhfrc_tracts.zip"
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
                p = shp.with_suffix(ext)
                if p.exists():
                    z.write(p, p.name)
        return zip_path
    raise SystemExit("No layer to publish. Run build_arcgis_layer.py first.")


def _connect_gis():
    """Return an authenticated arcgis.gis.GIS instance."""
    from arcgis.gis import GIS

    username = os.environ.get("ARCGIS_USERNAME")
    password = os.environ.get("ARCGIS_PASSWORD")
    token = os.environ.get("ARCGIS_TOKEN")

    if username and password:
        print(f"  Authenticating as '{username}' (env vars).")
        return GIS("https://www.arcgis.com", username, password)
    if token:
        print("  Authenticating via ARCGIS_TOKEN env var.")
        return GIS("https://www.arcgis.com", token=token)
    # Interactive OAuth: opens browser
    print("  No env-var credentials found — falling back to interactive OAuth.")
    print("  A browser window will open for sign-in.")
    return GIS("https://www.arcgis.com", client_id="arcgisonline")


def publish(
    title: str = DEFAULT_TITLE,
    tags: list[str] | None = None,
    snippet: str = DEFAULT_SNIPPET,
    overwrite_existing: bool = True,
    target_sr: int = 4326,
) -> None:
    tags = tags or DEFAULT_TAGS
    upload = _pick_upload_path()
    print(f"Uploading: {upload.name}  ({upload.stat().st_size / 1024:.1f} KB)")

    gis = _connect_gis()
    print(f"  Signed in as: {gis.users.me.username} @ {gis.url}")

    existing = None
    if overwrite_existing:
        hits = gis.content.search(
            query=f'title:"{title}" owner:{gis.users.me.username} '
            f'type:"Feature Service"',
            max_items=5,
        )
        if hits:
            existing = hits[0]
            print(f"  Found existing service: {existing.id} — will overwrite.")

    if existing is not None:
        # Overwrite in place — preserves item id, URL, sharing, and any
        # Dashboard that already references this layer.
        from arcgis.features import FeatureLayerCollection

        flc = FeatureLayerCollection.fromitem(existing)
        try:
            result = flc.manager.overwrite(str(upload))
            print(f"  Overwrite ok: {result}")
        except Exception as e:
            raise SystemExit(f"Overwrite failed: {e}")
        published = existing
    else:
        # Fresh publish: create Item, publish to Feature Service.
        # targetSR pinned to the source GPKG's CRS (WGS84, wkid 4326)
        # so AGOL does NOT silently reproject to Web Mercator and end
        # up with an extent tagged 102100 but populated with lat/lon
        # numbers — the metadata mismatch that broke tract rendering
        # on v4 (SDK reads extent as a ~1.6 meter box at (0,0) and
        # never fetches tiles for the TN view).
        item_props = {
            "type": "GeoPackage" if upload.suffix == ".gpkg" else "Shapefile",
            "title": title,
            "tags": ",".join(tags),
            "snippet": snippet,
        }
        # AGOL rejects (409) if an item with the same *filename* already
        # exists in this user's content. Derive a unique upload name
        # from the title so re-runs against the same GPKG land as
        # distinct items (v3, v4, v5 all coexist without collision).
        import re as _re

        safe = _re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_").lower()
        upload_name = f"{safe}{upload.suffix}"
        added = gis.content.add(item_props, str(upload), filename=upload_name)
        print(f"  Uploaded item: {added.id}  (name: {upload_name})")
        publish_params = {"targetSR": {"wkid": target_sr}}
        print(f"  Publishing with targetSR={target_sr} (matches source GPKG)")
        published = added.publish(publish_parameters=publish_params)
        print(f"  Published feature service: {published.id}")

    print(f"\nItem URL:    {published.homepage}")
    print(f"REST URL:    {published.url}")
    print(
        "\nSharing is set to PRIVATE by default. In AGOL, open the item, "
        "click 'Share', and pick Everyone (public) / your org / group as "
        "appropriate. If you want it public, share BOTH this Feature Layer "
        "AND any Dashboard that references it — otherwise anonymous viewers "
        "see an empty map."
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Publish (or overwrite) the JHFRC tract Feature Layer on ArcGIS Online.",
    )
    ap.add_argument("--title", default=DEFAULT_TITLE, help="Item title in AGOL.")
    ap.add_argument(
        "--tag",
        action="append",
        default=None,
        help="Extra tag (repeatable). Combined with the default tag set.",
    )
    ap.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Force a fresh publish even if a matching item exists.",
    )
    ap.add_argument(
        "--target-sr",
        type=int,
        default=4326,
        help=(
            "Feature service spatial reference wkid (default 4326 = WGS84). "
            "Only used on fresh publish. Passing anything other than 4326 "
            "risks the extent-metadata mismatch that broke v4."
        ),
    )
    args = ap.parse_args(argv)

    tags = list(DEFAULT_TAGS)
    if args.tag:
        tags.extend(args.tag)
    publish(
        title=args.title,
        tags=tags,
        overwrite_existing=not args.no_overwrite,
        target_sr=args.target_sr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
