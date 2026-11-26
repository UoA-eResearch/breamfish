#!/usr/bin/env python3
"""Fetch the public records of where snapper have been found in the bay, and reduce
them to the small table the habitat index is checked against.

    python3 scripts/fetch_habitat_points.py

Writes src/breamfish/species/snapper_records.csv, which is committed: one row per
place and time (a tagging station, a trawl tow, a sighting), not per fish. The raw
answers are kept under data/habitat/raw/ (not committed); delete a file there to fetch
it again. Standard library only.

These records are not used to build the index. They are the only independent thing to
test it against, and they are thin: see docs/habitat.md.

Sources (docs/data-sources.md):
- OBIS, api.obis.org: the Ministry for Primary Industries tag database and NIWA's
  research trawl records (CC BY 4.0), and a 1901 trawl (CC0).
- iNaturalist, api.inaturalist.org: research-grade observations whose observer chose
  CC0 or CC BY. Observations under other licences are not copied here.
"""

from __future__ import annotations

import csv
import json
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "habitat" / "raw"
OUT = ROOT / "src" / "breamfish" / "species" / "snapper_records.csv"

USER_AGENT = "breamfish/0.1 (+https://github.com/UoA-eResearch/breamfish)"

# The study box (docs/data-sources.md).
WEST, SOUTH, EAST, NORTH = 174.38, -36.12, 174.80, -35.78

OBIS = "https://api.obis.org/v3/occurrence"
# OBIS files snapper under its older name; Chrysophrys auratus returns nothing.
OBIS_NAME = "Pagrus auratus"
INATURALIST = "https://api.inaturalist.org/v1/observations"
INATURALIST_TAXON = 530886  # Chrysophrys auratus

# OBIS dataset name -> (short key, method). Datasets not listed are not used: the
# iNaturalist copy in OBIS is CC BY-NC, and one record describes a whole island.
OBIS_DATASETS = {
    "Ministry for Primary Industries Tag Database": ("tagging", "caught for tagging"),
    "MBIS research trawl surveys": ("trawl", "research trawl"),
    "NZ research trawl surveys since 2008": ("trawl", "research trawl"),
    "Experimental trawling off New Zealand. 1901": ("trawl", "research trawl"),
    "Near-shore reef fishes in northern New Zealand": ("divers", "diver survey"),
}
OPEN_LICENCES = {"cc0", "cc-by"}
# A record whose position is stated to be less sure than this is left out.
MAX_UNCERTAINTY_M = 1000
MAX_SIGHTING_ACCURACY_M = 200

FIELDS = ("source", "station", "lon", "lat", "year", "month", "records", "method", "licence")


def get(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def cached(name: str, fetch) -> list[dict]:
    path = RAW / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"results": fetch()}))
    return json.loads(path.read_text())["results"]


def fetch_obis() -> list[dict]:
    box = f"POLYGON(({WEST} {SOUTH},{EAST} {SOUTH},{EAST} {NORTH},{WEST} {NORTH},{WEST} {SOUTH}))"
    rows, after = [], None
    while True:
        query = {"scientificname": OBIS_NAME, "geometry": box, "size": 5000}
        if after:
            query["after"] = after
        page = get(f"{OBIS}?{urllib.parse.urlencode(query)}")["results"]
        rows += page
        if len(page) < 5000:
            return rows
        after = page[-1]["id"]


def fetch_inaturalist() -> list[dict]:
    rows, page = [], 1
    while True:
        query = {
            "taxon_id": INATURALIST_TAXON,
            "swlat": SOUTH,
            "swlng": WEST,
            "nelat": NORTH,
            "nelng": EAST,
            "quality_grade": "research",
            "per_page": 200,
            "page": page,
            "order_by": "id",
        }
        answer = get(f"{INATURALIST}?{urllib.parse.urlencode(query)}")
        rows += answer["results"]
        if len(rows) >= answer["total_results"] or not answer["results"]:
            return rows
        page += 1


def year_month(date: str) -> tuple[str, str]:
    """Year and month of an event date, blank where it does not name one month.

    "1993-11-21T05:30+12" is November 1993; "1990-06/1993-04" is a span of years and
    names none.
    """
    first = date.split("/")[0]
    last = date.split("/")[-1]
    if len(first) < 7 or first[:7] != last[:7] or not first[:4].isdigit():
        return (first[:4] if first[:4].isdigit() and first[:4] == last[:4] else "", "")
    return first[:4], str(int(first[5:7]))


def obis_stations(rows: list[dict]) -> list[dict]:
    """One row per station: a tagging set or a trawl tow, however many fish it took."""
    stations: dict[tuple, dict] = {}
    count: dict[tuple, int] = defaultdict(int)
    for row in rows:
        dataset = OBIS_DATASETS.get(row.get("datasetName"))
        if dataset is None or row.get("occurrenceStatus") != "present":
            continue
        if (row.get("coordinateUncertaintyInMeters") or 0) > MAX_UNCERTAINTY_M:
            continue
        source, method = dataset
        year, month = year_month(row.get("eventDate") or "")
        lon, lat = row["decimalLongitude"], row["decimalLatitude"]
        station = row.get("fieldNumber") or f"{lon:.4f},{lat:.4f}"
        key = (source, station, year, month)
        count[key] += 1
        stations.setdefault(
            key,
            {
                "source": source,
                "station": station,
                "lon": f"{lon:.5f}",
                "lat": f"{lat:.5f}",
                "year": year,
                "month": month,
                "method": method,
                "licence": "CC0" if "1901" in row["datasetName"] else "CC BY 4.0",
            },
        )
    return [{**station, "records": count[key]} for key, station in stations.items()]


def sightings(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        accuracy = row.get("positional_accuracy")
        if (
            row.get("license_code") not in OPEN_LICENCES
            or row.get("obscured")
            or accuracy is None
            or accuracy > MAX_SIGHTING_ACCURACY_M
            or not row.get("observed_on")
        ):
            continue
        lon, lat = row["geojson"]["coordinates"]
        year, month = year_month(row["observed_on"])
        out.append(
            {
                "source": "sighting",
                "station": f"inaturalist/{row['id']}",
                "lon": f"{float(lon):.5f}",
                "lat": f"{float(lat):.5f}",
                "year": year,
                "month": month,
                "records": 1,
                "method": "photographed (iNaturalist)",
                "licence": {"cc0": "CC0", "cc-by": "CC BY 4.0"}[row["license_code"]],
            }
        )
    return out


def main() -> int:
    rows = obis_stations(cached("obis_snapper.json", fetch_obis))
    rows += sightings(cached("inaturalist_snapper.json", fetch_inaturalist))
    rows.sort(key=lambda r: (r["source"], r["year"], r["month"].zfill(2), r["station"]))
    if not rows:
        print("no records: existing file left alone", file=sys.stderr)
        return 1
    with OUT.open("w", newline="") as handle:
        handle.write(
            "# Places and times snapper (Chrysophrys auratus) were recorded in the bay.\n"
            "# Written by scripts/fetch_habitat_points.py; do not edit by hand.\n"
            "# tagging, trawl, divers: OBIS (obis.org), from the Ministry for Primary\n"
            "#   Industries tag database and NIWA research trawl and survey records.\n"
            "# sighting: iNaturalist (inaturalist.org) research-grade observations, by\n"
            "#   their observers; the station is the observation's number.\n"
        )
        writer = csv.DictWriter(handle, FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    by_source = defaultdict(int)
    for row in rows:
        by_source[row["source"]] += 1
    print(f"{OUT.relative_to(ROOT)}: {len(rows)} rows", dict(by_source))
    return 0


if __name__ == "__main__":
    sys.exit(main())
