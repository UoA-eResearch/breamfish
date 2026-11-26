#!/usr/bin/env python3
"""Fetch the small static map layers and write them as GeoJSON for the frontend.

These layers change rarely, so they are fetched by hand and committed rather
than requested by every visitor:

  web/public/layers/reserves.geojson   DOC marine reserves (no-take areas)
  web/public/layers/ramps.geojson      boat ramps and slipways from OpenStreetMap

Run from the repo root:  python3 scripts/fetch_static_layers.py
Standard library only.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "breamfish/0.1 (+https://github.com/UoA-eResearch/breamfish)"

# A little wider than the study box so reserves on the edge are not clipped.
WEST, SOUTH, EAST, NORTH = 174.30, -36.20, 174.85, -35.70

OUT_DIR = Path(__file__).resolve().parent.parent / "web" / "public" / "layers"

DOC_RESERVES = (
    "https://services1.arcgis.com/3JjYDyG3oajxU6HO/arcgis/rest/services/"
    "DOC_Marine_Reserves/FeatureServer/0/query"
)
# Public Overpass instances, tried in order; any one of them is enough.
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)


def http_get(url: str, data: bytes | None = None) -> bytes:
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def round_coords(value, places: int = 6):
    """Round every number in a nested coordinate list (keeps the files small)."""
    if isinstance(value, (int, float)):
        return round(value, places)
    return [round_coords(item, places) for item in value]


def fetch_reserves() -> dict:
    params = {
        "where": "1=1",
        "geometry": f"{WEST},{SOUTH},{EAST},{NORTH}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "outSR": "4326",
        "f": "geojson",
    }
    raw = json.loads(http_get(f"{DOC_RESERVES}?{urllib.parse.urlencode(params)}"))
    features = []
    for feature in raw.get("features", []):
        props = feature.get("properties") or {}
        name = next(
            (str(v) for k, v in props.items() if k.lower() in {"name", "reserve_name"} and v),
            "Marine reserve",
        )
        geometry = feature["geometry"]
        geometry["coordinates"] = round_coords(geometry["coordinates"])
        features.append(
            {
                "type": "Feature",
                "properties": {"name": name, "rule": "No-take: all fishing prohibited"},
                "geometry": geometry,
            }
        )
    return {
        "type": "FeatureCollection",
        "metadata": {
            "source": "Department of Conservation, DOC Marine Reserves",
            "source_url": DOC_RESERVES,
            "licence": "CC BY 4.0, Department of Conservation",
            "fetched": dt.date.today().isoformat(),
            "note": "Indicative only. The legal boundary is the reserve's Order in Council.",
        },
        "features": features,
    }


def fetch_ramps() -> dict:
    query = (
        "[out:json][timeout:60];"
        f'(node["leisure"="slipway"]({SOUTH},{WEST},{NORTH},{EAST});'
        f'way["leisure"="slipway"]({SOUTH},{WEST},{NORTH},{EAST}););'
        "out center tags;"
    )
    body = urllib.parse.urlencode({"data": query}).encode()
    raw, errors = None, []
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            raw = json.loads(http_get(endpoint, body))
            break
        except (OSError, ValueError) as error:  # HTTP errors, timeouts, bad JSON
            errors.append(f"{endpoint}: {error}")
    if raw is None:
        raise RuntimeError("every Overpass endpoint failed: " + "; ".join(errors))
    features = []
    for element in raw.get("elements", []):
        lon = element.get("lon", (element.get("center") or {}).get("lon"))
        lat = element.get("lat", (element.get("center") or {}).get("lat"))
        if lon is None or lat is None:
            continue
        tags = element.get("tags") or {}
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "name": tags.get("name", "Boat ramp"),
                    "osm": f"{element['type']}/{element['id']}",
                },
                "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            }
        )
    features.sort(key=lambda f: f["properties"]["osm"])
    return {
        "type": "FeatureCollection",
        "metadata": {
            "source": "OpenStreetMap contributors (leisure=slipway)",
            "source_url": "https://www.openstreetmap.org/copyright",
            "licence": "ODbL 1.0",
            "fetched": dt.date.today().isoformat(),
        },
        "features": features,
    }


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    failed = 0
    for filename, fetch in (("reserves.geojson", fetch_reserves), ("ramps.geojson", fetch_ramps)):
        try:
            collection = fetch()
        except (OSError, ValueError, RuntimeError) as error:
            print(f"{filename}: FAILED, existing file left alone ({error})")
            failed += 1
            continue
        if not collection["features"]:
            print(f"{filename}: no features returned, existing file left alone")
            failed += 1
            continue
        (OUT_DIR / filename).write_text(json.dumps(collection, separators=(",", ":")) + "\n")
        print(f"{filename}: {len(collection['features'])} features")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
