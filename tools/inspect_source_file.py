"""Find the original filename + type of the currently-published JHFRC
Feature Layer's source item, so we can match it exactly on overwrite.

AGOL's FeatureLayerCollection.manager.overwrite() insists the incoming
file have the same name + extension as the file originally uploaded to
publish the layer. This one-off script prints that name.

Usage:
    python tools/inspect_source_file.py            # searches by default title
    python tools/inspect_source_file.py <itemid>   # inspects that item directly
"""
from __future__ import annotations

import os
import sys

TITLE = "JHFRC Tracts"


def _connect():
    from arcgis.gis import GIS

    u = os.environ.get("ARCGIS_USERNAME")
    p = os.environ.get("ARCGIS_PASSWORD")
    if not (u and p):
        raise SystemExit("Set ARCGIS_USERNAME + ARCGIS_PASSWORD first.")
    return GIS("https://www.arcgis.com", u, p)


def main(argv: list[str]) -> int:
    gis = _connect()
    print(f"Signed in as: {gis.users.me.username}")

    item = None
    if len(argv) > 1:
        item = gis.content.get(argv[1])
        if item is None:
            raise SystemExit(f"No item found with id: {argv[1]}")
    else:
        # Grab any Feature Service the user owns with the default title.
        hits = gis.content.search(
            query=f'title:"{TITLE}" owner:{gis.users.me.username} type:"Feature Service"',
            max_items=10,
        )
        if not hits:
            raise SystemExit(f"No Feature Service found titled '{TITLE}'.")
        item = hits[0]

    print(f"\nItem: {item.title}  ({item.id})")
    print(f"Type: {item.type}")
    print(f"URL:  {item.url}")
    # Item.related_items('Service2Data', 'reverse') gives the source data item.
    related = item.related_items("Service2Data", "reverse") or []
    print(f"\nRelated source-data items: {len(related)}")
    for r in related:
        # r.type is "GeoPackage", "Shapefile", "CSV", etc.
        # r.name is the file name AGOL stored.
        name = getattr(r, "name", None) or "(no .name)"
        print(f"  - id={r.id} type={r.type!r} name={name!r} title={r.title!r}")
    # Fallback: FeatureLayerCollection.properties may hint at source
    try:
        from arcgis.features import FeatureLayerCollection

        flc = FeatureLayerCollection.fromitem(item)
        sr_meta = flc.properties.get("sourceServiceMetaData") or {}
        print(f"\nsourceServiceMetaData: {dict(sr_meta) if sr_meta else '(none)'}")
    except Exception as e:
        print(f"(could not read FLC properties: {e})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
