#!/usr/bin/env python3
"""Build the "boats seen from space" layer from the cluster's Sentinel-2 boat count.

Run by hand from the repo root when the count has been run again on the cluster:

    uv run python scripts/build_boats.py SITE_JSON

SITE_JSON is the file the cluster's boats-map.py writes (site.json), as a path or as
the address it is published at (the results container, under boats/site.json). It
writes

    web/public/boats/boats.geojson   one 1 km square per feature, counts and colour band
    web/public/boats/manifest.json   everything the site prints about the layer

Review the diff and commit those. The count, and how its answers were checked, is
described in docs/boats.md. Standard library only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "public" / "boats"
USER_AGENT = "breamfish/0.1 (+https://github.com/UoA-eResearch/breamfish)"

GROUPS = {
    "all": "All passes",
    "weekend": "Weekends and holidays",
    "weekday": "Weekdays",
}

# Colour bands, in boats seen per 100 passes on which the square was clear. The same
# bands for every group, so weekends and weekdays can be compared by colour. Band 0 is
# "clear on enough passes, no boat seen". Judgement: doubling steps, so each band is
# about twice as busy as the one below, starting at 1.5 so that a single boat in a
# group's passes (about 75 to 240 clear passes a square) stays in the lowest band. On all
# passes the top band held the busiest 1% of squares in the build of 28 November 2026.
BREAKS = [1.5, 3.0, 6.0, 12.0]

# The hand check of the answers kept, from the cluster's runbook (docs/runbook.md in
# nectar-vhpc, "Counting boats from Sentinel-2"): a random sample of 60 accepted boats,
# drawn after the checks were fixed and not used to set them, each picture judged by eye
# by Claude, the AI assistant that built the count, on 28 November 2026. Not by a person.
CHECK = {
    "sample": 60,
    "certain": 34,
    "likely": 18,
    "cloud_or_rock": 3,
    "unclear": 5,
    "judged_by": "Claude, the AI assistant that built the count, by eye, on 28 November 2026",
    "note": (
        "Certain: a hull or a wake can be seen. Likely: a lone bright spot on open water, "
        "which is how a small boat at rest looks at this resolution."
    ),
}

LIMITS = [
    "Every picture is taken at about 11:25 New Zealand time, when the satellite passes, "
    "every few days at most. Where boats are at dawn, at dusk or at night is not in it.",
    "Its pixels are 10 m across, so it sees a boat mostly by its wake. Boats at anchor or "
    "drifting are counted less often than boats under way.",
    "Many boats in the busiest places are going somewhere, not fishing: the harbour channel "
    "is busy because every boat leaving the harbour uses it.",
    "Rough days and cloudy days are left out, so this is where boats are on fine days.",
    "Moored boats, rocks and buoys are in the same place on most passes. Such places are "
    "marked and the boats right by them are not counted.",
    "Most open-water squares hold only a few boats in all the years, so the pattern is "
    "broad. A difference of one or two boats between neighbouring squares means nothing.",
]


def load(source: str) -> dict:
    if source.startswith("https://"):
        request = urllib.request.Request(source, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    return json.loads(Path(source).read_text())


def band(boats: int, seen: int) -> int:
    """0 for none seen, then 1 to 5 by boats per 100 clear passes."""
    if boats == 0:
        return 0
    rate = 100.0 * boats / seen
    return 1 + sum(rate > limit for limit in BREAKS)


def band_labels() -> list[str]:
    def n(value: float) -> str:
        return f"{value:g}"

    labels = ["Clear water, no boat seen"]
    labels.append(f"Up to {n(BREAKS[0])} per 100 passes")
    labels += [f"{n(lo)} to {n(hi)}" for lo, hi in zip(BREAKS, BREAKS[1:], strict=False)]
    labels.append(f"Over {n(BREAKS[-1])}")
    return labels


def check(site: dict) -> None:
    """Refuse a file that is not what boats-map.py writes, or does not add up."""
    if site.get("schema") != 1:
        raise ValueError(f"unknown schema {site.get('schema')!r}")
    squares = site["squares"]
    if not squares:
        raise ValueError("no squares")
    for i, square in enumerate(squares):
        ring = square["ring"]
        inside = all(174.0 < lon < 175.2 and -36.4 < lat < -35.5 for lon, lat in ring)
        if len(ring) != 4 or not inside:
            raise ValueError(f"square {i}: corners outside the bay: {ring}")
        for group in GROUPS:
            counts = square[group]
            if not (isinstance(counts["seen"], int) and isinstance(counts["boats"], int)):
                raise ValueError(f"square {i}: counts are not whole numbers")
            if counts["seen"] < 0 or counts["boats"] < 0:
                raise ValueError(f"square {i}: a negative count")
        if square["weekend"]["boats"] + square["weekday"]["boats"] != square["all"]["boats"]:
            raise ValueError(f"square {i}: weekend and weekday boats do not add up to all")
        if square["all"]["seen"] == 0:
            raise ValueError(f"square {i}: never seen clear")
    summary = site["summary"]
    for group in GROUPS:
        listed = sum(s[group]["boats"] for s in squares)
        if listed > summary["boats"][group]:
            counted = summary["boats"][group]
            raise ValueError(
                f"{group}: more boats in the squares ({listed}) than counted ({counted})"
            )


def build(site: dict, built: str) -> tuple[dict, dict]:
    check(site)
    features = []
    for square in site["squares"]:
        props: dict = {"fixed": bool(square["fixed"])}
        for group in GROUPS:
            seen, boats = square[group]["seen"], square[group]["boats"]
            props[f"{group}_seen"] = seen
            props[f"{group}_boats"] = boats
            # A square must be clear on some passes of the group for its colour to mean anything.
            props[f"{group}_band"] = band(boats, seen) if seen else -1
        ring = [list(corner) for corner in square["ring"]]
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring + [ring[0]]]},
                "properties": props,
            }
        )
    geojson = {"type": "FeatureCollection", "features": features}

    summary = site["summary"]
    shown = {group: sum(f["properties"][f"{group}_boats"] for f in features) for group in GROUPS}
    manifest = {
        "built": built,
        "file": "boats.geojson",
        "made_on_cluster": site["made"],
        "square_m": site["square_m"],
        "first_pass": site["first_pass"],
        "last_pass": site["last_pass"],
        "groups": [
            {
                "id": group,
                "label": label,
                "passes": summary["passes"][group],
                "boats": shown[group],
                "boats_per_pass": round(shown[group] / max(summary["passes"][group], 1), 1),
            }
            for group, label in GROUPS.items()
        ],
        "passes_left_out": summary["scenes_left_out"],
        "bands": {"breaks_per_100_passes": BREAKS, "labels": band_labels()},
        "squares": len(features),
        "fixed_squares": sum(f["properties"]["fixed"] for f in features),
        "check": CHECK,
        "source": {
            "label": (
                "Copernicus Sentinel-2 L2A, tile 60HTF, read from the public archive on AWS "
                "(Earth Search catalogue)"
            ),
            "url": "https://registry.opendata.aws/sentinel-2-l2a-cogs/",
            # The credit the Copernicus data terms ask for, with the years used.
            "licence": (
                f"Contains modified Copernicus Sentinel data {site['first_pass'][:4]}"
                f"\u2013{site['last_pass'][:4]}"
            ),
        },
        "how": (
            "Every Sentinel-2 picture of the bay with less than 60% cloud was searched for "
            "small spots brighter than the water around them, on clear open water at least "
            "200 m from shore. An open-weights vision model (Qwen3-VL-8B), shown a few "
            "labelled examples first, was asked whether each spot was a boat, cloud, a wave "
            "or something else. Its boat answers were kept only where five further checks "
            "agreed: the spot covers at least 3 pixels, it is bright enough, there is no "
            "cloud within 1 km, the sea that day was not too rough to tell, and the place is "
            "not one where something is seen on most passes. Each square's figure is the "
            "boats seen in it for every 100 passes on which it was clear."
        ),
        "limits": LIMITS,
    }
    return geojson, manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("site", help="site.json from the cluster: a path or its https:// address")
    args = parser.parse_args(argv)
    site = load(args.site)
    geojson, manifest = build(site, dt.date.today().isoformat())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "boats.geojson").write_text(json.dumps(geojson, separators=(",", ":")) + "\n")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    groups = ", ".join(
        f"{g['label'].lower()} {g['boats']} in {g['passes']} passes" for g in manifest["groups"]
    )
    fixed = manifest["fixed_squares"]
    print(f"{manifest['squares']} squares ({fixed} with a fixed object); {groups}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
