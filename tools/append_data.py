"""Append the JHFRC GPKG source item's data into the (empty)
jhfrc_census_tracts_v2 hosted feature layer.

Runs the AGOL /append REST endpoint directly because arcgis-python's
FeatureLayer.append swallows job errors. Polls the job status and
prints the final row count.

Env:
    ARCGIS_USERNAME
    ARCGIS_PASSWORD

Constants (edit here if the service ever moves):
    SVC              — FeatureServer URL
    SRC_ITEM_ID      — GPKG item id (source data)
    SOURCE_TABLE     — internal table name inside the GPKG
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request

SVC = (
    "https://services.arcgis.com/UnTXoPXBYERF0OH6/arcgis/rest/services/"
    "jhfrc_census_tracts_v2/FeatureServer"
)
SRC_ITEM_ID = "2ba6259fc21648ff823245142697bb8a"
SOURCE_TABLE = "jhfrc_tracts"


def main() -> int:
    from arcgis.gis import GIS
    import requests

    user = os.environ.get("ARCGIS_USERNAME")
    pw = os.environ.get("ARCGIS_PASSWORD")
    if not (user and pw):
        raise SystemExit("Set ARCGIS_USERNAME + ARCGIS_PASSWORD first.")

    gis = GIS("https://www.arcgis.com", user, pw)
    token = gis._con.token

    r = requests.post(
        f"{SVC}/0/append",
        data={
            "appendItemId": SRC_ITEM_ID,
            "appendUploadFormat": "geoPackage",
            "sourceTableName": SOURCE_TABLE,
            "upsert": "false",
            "skipInserts": "false",
            "skipUpdates": "true",
            "rollbackOnFailure": "true",
            "f": "json",
            "token": token,
        },
        timeout=120,
    )
    resp = r.json()
    print("Response:", json.dumps(resp, indent=2))

    status_url = resp.get("statusUrl")
    if not status_url:
        print("No statusUrl in response — the append call did not start.")
        return 1

    final = None
    for i in range(60):
        time.sleep(3)
        s = requests.get(
            status_url, params={"f": "json", "token": token}, timeout=30,
        ).json()
        st = (s.get("status") or "").lower()
        print(
            f"poll {i}: status={s.get('status')} "
            f"rec={s.get('recordCount')} msg={s.get('statusMessage', '')}"
        )
        if st in ("completed", "failed"):
            final = s
            print("FINAL:", json.dumps(s, indent=2))
            break

    q = f"{SVC}/0/query?" + urllib.parse.urlencode(
        {"where": "1=1", "returnCountOnly": "true", "f": "json"}
    )
    print("Row count now:", urllib.request.urlopen(q).read().decode())
    return 0 if (final and (final.get("status") or "").lower() == "completed") else 1


if __name__ == "__main__":
    sys.exit(main())
