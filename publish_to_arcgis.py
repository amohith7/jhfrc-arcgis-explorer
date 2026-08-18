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


def _pick_upload_path(explicit: str | None = None, prefer: str = "gpkg") -> Path:
    """Pick which of the built layer artifacts to upload.

    Priority: explicit path > preferred format > fallback format. When
    overwriting an existing hosted feature layer, AGOL is happiest when
    the incoming file matches the format the layer was originally
    published from. Pass --file to override, or --format shp when the
    default GPKG upload gets a "Job failed" from AGOL's overwrite.
    """
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = DATA_DIR / p
        if not p.exists():
            raise SystemExit(f"--file not found: {p}")
        return p
    gpkg = DATA_DIR / "jhfrc_tracts.gpkg"
    shp = DATA_DIR / "jhfrc_tracts.shp"
    zip_path = DATA_DIR / "jhfrc_tracts.zip"
    order = [gpkg, zip_path] if prefer == "gpkg" else [zip_path, gpkg]
    for candidate in order:
        if candidate.exists():
            # If we chose "shp" but only the raw .shp is present, zip
            # it fresh so AGOL accepts it.
            if candidate == zip_path and not zip_path.exists() and shp.exists():
                import zipfile

                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
                    for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
                        p = shp.with_suffix(ext)
                        if p.exists():
                            z.write(p, p.name)
            return candidate
    # Zip the shapefile bundle on-demand if that's the only thing left.
    if shp.exists():
        import zipfile

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
    file: str | None = None,
    prefer_format: str = "gpkg",
) -> None:
    tags = tags or DEFAULT_TAGS
    upload = _pick_upload_path(explicit=file, prefer=prefer_format)
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
        item_props = {
            "type": "GeoPackage" if upload.suffix == ".gpkg" else "Shapefile",
            "title": title,
            "tags": ",".join(tags),
            "snippet": snippet,
        }
        added = gis.content.add(item_props, str(upload))
        print(f"  Uploaded item: {added.id}")
        published = added.publish()
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
        "--file",
        default=None,
        help="Explicit file to upload (absolute path or relative to data/). "
        "Bypasses format auto-detection.",
    )
    ap.add_argument(
        "--format",
        dest="prefer_format",
        default="gpkg",
        choices=("gpkg", "shp"),
        help="Preferred format when auto-picking (default: gpkg). Try 'shp' "
        "if 'Job failed' errors persist on overwrite — AGOL is most "
        "reliable when the incoming format matches the layer's original.",
    )
    args = ap.parse_args(argv)

    tags = list(DEFAULT_TAGS)
    if args.tag:
        tags.extend(args.tag)
    publish(
        title=args.title,
        tags=tags,
        overwrite_existing=not args.no_overwrite,
        file=args.file,
        prefer_format=args.prefer_format,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
