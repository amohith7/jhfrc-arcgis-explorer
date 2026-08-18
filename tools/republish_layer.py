"""End-to-end republish: delete any stale JHFRC feature service +
source item, upload the fresh GPKG, publish it, share it public,
and print the final REST URL for the dashboard.

Env:
    ARCGIS_USERNAME
    ARCGIS_PASSWORD

Behavior:
    1. Delete every FeatureService the current user owns whose service
       name matches SERVICE_NAME (any casing).
    2. Delete every GeoPackage item titled SERVICE_NAME the current
       user owns (so the new upload isn't rejected as "already
       published from this source").
    3. Upload data/<service_name>.gpkg as a new GeoPackage item.
    4. Publish it to a Feature Service, forcing the exact service
       name so the URL is stable.
    5. Poll the async job for the real error message instead of the
       "Job failed." wrapper.
    6. Share the resulting feature service to Everyone (Public).
    7. Print the REST URL — copy the trailing "/0" into dashboard's
       LAYER_URL constant.
"""
from __future__ import annotations

import json
import os
import sys
import time

SERVICE_NAME = "jhfrc_census_tracts_v2"
DEFAULT_TITLE = "JHFRC Tracts"


def main() -> int:
    from pathlib import Path
    from arcgis.gis import GIS
    import requests

    user = os.environ.get("ARCGIS_USERNAME")
    pw = os.environ.get("ARCGIS_PASSWORD")
    if not (user and pw):
        raise SystemExit("Set ARCGIS_USERNAME + ARCGIS_PASSWORD first.")

    repo = Path(__file__).resolve().parent.parent
    gpkg = repo / "data" / f"{SERVICE_NAME}.gpkg"
    if not gpkg.exists():
        raise SystemExit(f"Missing: {gpkg}\nRun `python build_arcgis_layer.py` first.")

    gis = GIS("https://www.arcgis.com", user, pw)
    me = gis.users.me
    token = gis._con.token
    print(f"Signed in as: {me.username}")

    # 1. Delete stale feature services matching our service name.
    hits = gis.content.search(
        query=f'owner:{me.username} type:"Feature Service"', max_items=200,
    )
    for h in hits:
        if h.url and h.url.rstrip("/").split("/")[-2].lower() == SERVICE_NAME.lower():
            print(f"Deleting stale service: {h.title} ({h.id})")
            h.delete()

    # 2. Delete stale GeoPackage items so publish doesn't refuse.
    for gp in gis.content.search(
        query=f'owner:{me.username} type:"GeoPackage"', max_items=200,
    ):
        if gp.title in {SERVICE_NAME, DEFAULT_TITLE}:
            print(f"Deleting stale GPKG item: {gp.title} ({gp.id})")
            gp.delete()

    # 3. Upload fresh GPKG. Uses gis.content.add — emits a
    # DeprecationWarning under arcgis-python 2.3+ but works reliably
    # across versions, unlike me.folders which recently changed shape.
    print(f"Uploading: {gpkg}  ({gpkg.stat().st_size / 1024:.1f} KB)")
    added = gis.content.add(
        {
            "type": "GeoPackage",
            "title": SERVICE_NAME,
            "tags": "JHFRC,SDoH,census tract,community profiles",
            "snippet": "Tract-level SDoH indicators for the JHFRC service region.",
        },
        str(gpkg),
    )
    src_item = added
    print(f"Uploaded item: {src_item.id}")

    # 4. Publish, hitting the REST endpoint directly so we can poll for
    # real errors. arcgis-python's src.publish() swallows job errors as
    # generic "Job failed."
    #
    # AGOL holds a deleted service's name in reserve for a short
    # cooldown, so a fresh-publish attempt that reuses the just-deleted
    # name intermittently fails with "Service name X already exists".
    # Auto-retry with an incrementing suffix so we always land a URL,
    # then the caller can update the dashboard's LAYER_URL accordingly.
    base = f"{gis.url}/sharing/rest/content/users/{me.username}"
    pub_url = f"{base}/publish"

    def try_publish(name: str) -> dict:
        print(f"Publish attempt: name={name!r}")
        return requests.post(
            pub_url,
            data={
                "itemid": src_item.id,
                "filetype": "geoPackage",
                "publishParameters": json.dumps(
                    {"name": name, "targetSR": {"wkid": 4326}}
                ),
                "f": "json",
                "token": token,
            },
            timeout=120,
        ).json()

    # Try the base name, then _v3.._v9 as fallbacks. Suffix increments
    # only trigger when the base already-exists error comes back.
    resp = None
    final_name = None
    candidate_names = [SERVICE_NAME]
    if SERVICE_NAME.endswith("_v2"):
        stem = SERVICE_NAME[:-3]
        candidate_names += [f"{stem}_v{n}" for n in range(3, 10)]
    else:
        candidate_names += [f"{SERVICE_NAME}_v{n}" for n in range(2, 10)]

    for name in candidate_names:
        resp = try_publish(name)
        svcs = resp.get("services") or []
        if svcs and svcs[0].get("success") is not False:
            final_name = name
            break
        err = (svcs[0].get("error") or {}) if svcs else {}
        msg = err.get("message", "")
        print(f"  -> failed: {msg}")
        if "already exists" not in msg:
            # Non-recoverable error — clean up the uploaded source item
            # and bail with the real error so we don't leave orphans.
            src_item.delete()
            raise SystemExit(f"Publish failed with unrecoverable error: {msg}")
        # AGOL cooldown — wait and try the next name.
        time.sleep(5)
    if final_name is None:
        src_item.delete()
        raise SystemExit(
            "Ran out of candidate names — every attempt hit 'already exists'."
        )

    print("Publish response:", json.dumps(resp, indent=2))
    services = resp.get("services") or []
    svc_entry = services[0]
    svc_item_id = svc_entry.get("serviceItemId")
    job_id = svc_entry.get("jobId")

    if job_id and svc_item_id:
        status_url = f"{base}/items/{svc_item_id}/status"
        for i in range(90):
            time.sleep(3)
            s = requests.get(
                status_url,
                params={
                    "jobId": job_id,
                    "jobType": "publish",
                    "f": "json",
                    "token": token,
                },
                timeout=30,
            ).json()
            st = (s.get("status") or "").lower()
            print(f"poll {i}: {s.get('status')}  {s.get('statusMessage','')}")
            if st in ("completed", "failed", "partial"):
                print("FINAL:", json.dumps(s, indent=2))
                if st != "completed":
                    raise SystemExit(1)
                break

    # 5. Share public + print URLs.
    svc = gis.content.get(svc_item_id)
    if svc is None:
        raise SystemExit(f"Could not locate published item {svc_item_id}")
    svc.share(everyone=True)
    print(f"\nItem URL : {svc.homepage}")
    print(f"REST URL : {svc.url}")
    from arcgis.features import FeatureLayer

    lyr = FeatureLayer(svc.url + "/0", gis=gis)
    print(f"Fields   : {len(lyr.properties.fields)}")
    # Row count sanity check.
    import urllib.parse, urllib.request

    q = (
        svc.url
        + "/0/query?"
        + urllib.parse.urlencode(
            {"where": "1=1", "returnCountOnly": "true", "f": "json"}
        )
    )
    print("Rows     :", urllib.request.urlopen(q).read().decode())
    return 0


if __name__ == "__main__":
    sys.exit(main())
