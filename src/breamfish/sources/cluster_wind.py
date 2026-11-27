"""The fine wind forecast run on our own cluster. Optional.

The public forecast works in squares about 8 by 10 km. A regional weather model
run on the cluster works at 1 km and publishes its 10 m wind, hour by hour, to an
address the server is told through the environment. With no address this source
does not exist: nothing is fetched and nothing is said about it.

The site never depends on it. When the run is missing, late or wrong, the map
goes on drawing the public forecast.
"""

import json
import math
import os
from datetime import UTC, datetime

from breamfish import config
from breamfish.sources.fetch import fetch_cached


def url() -> str | None:
    """Where the cluster publishes its newest run, or None if we have not been told."""
    return os.environ.get(config.FINE_WIND_ENV, "").strip() or None


def _frames(document: dict, key: str, hours: int, points: int) -> list:
    frames = document[key]
    if not isinstance(frames, list) or len(frames) != hours:
        raise ValueError(f"{key} does not have one entry for each hour")
    for frame in frames:
        if frame is None:
            continue
        if not isinstance(frame, list) or len(frame) != points:
            raise ValueError(f"{key} has an hour that does not match the grid")
        for value in frame:
            if value is None:
                continue
            good = isinstance(value, (int, float)) and not isinstance(value, bool)
            if not good or not math.isfinite(value) or abs(value) > config.FINE_WIND_MAX_KN:
                raise ValueError(f"{key} holds a value that cannot be a wind: {value!r}")
    return frames


def parse(body: bytes) -> dict:
    """Check the cluster's document and return what we use of it.

    It comes from a machine we run, but it is still read as something that may be
    half-written, out of date or simply wrong: everything the site would draw is
    checked here, and anything unexpected raises.
    """
    document = json.loads(body)
    if not isinstance(document, dict) or document.get("schema") != 1:
        raise ValueError("not a schema 1 wind document")
    if document.get("unit") != "kn":
        raise ValueError("winds are not in knots")

    hours = [datetime.strptime(h, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC) for h in document["hours"]]
    if not hours or sorted(set(hours)) != hours:
        raise ValueError("hours are missing, repeated or out of order")

    grid = document["grid"]
    nrows, ncols = grid["nrows"], grid["ncols"]
    lats, lons = grid["lats"], grid["lons"]
    if not (isinstance(nrows, int) and isinstance(ncols, int) and nrows >= 2 and ncols >= 2):
        raise ValueError("the grid has no size")
    rows_ok = len(lats) == nrows and len(lons) == nrows and all(len(row) == ncols for row in lons)
    if not rows_ok:
        raise ValueError("the grid's rows do not match its size")
    if any(south >= north for north, south in zip(lats, lats[1:], strict=False)):
        raise ValueError("the grid's rows do not run north to south")
    if any(east <= west for row in lons for west, east in zip(row, row[1:], strict=False)):
        raise ValueError("a grid row does not run west to east")

    source = document.get("source", {})
    return {
        "generated_at": datetime.strptime(document["generated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        ),
        "cycle": str(document.get("cycle", "")),
        "hours": hours,
        "grid": {"nrows": nrows, "ncols": ncols, "lats": lats, "lons": lons},
        "u": _frames(document, "u", len(hours), nrows * ncols),
        "v": _frames(document, "v", len(hours), nrows * ncols),
        "cell_km": [float(x) for x in source["cell_km"]],
        "model_km": float(source["model_km"]),
        "model": str(source.get("model", "")),
    }


def fetch(get, cache_dir, now) -> dict | None:
    """The newest run, as a fetch_cached result; None when no address is configured.

    A run made longer ago than config.FINE_WIND_MAX_AGE is not used, however
    recently it was fetched: the cluster has stopped, and an old forecast drawn as
    if it were new is worse than the coarser one that is up to date.
    """
    address = url()
    if address is None:
        return None
    result = fetch_cached(
        get,
        cache_dir,
        "cluster_wind.json",
        address,
        {},
        parse=parse,
        now=now,
        max_age=config.FINE_WIND_MAX_AGE,
    )
    if result["data"] is not None:
        made = result["data"]["generated_at"]
        if now - made > config.FINE_WIND_MAX_AGE:
            said = made.strftime("%Y-%m-%dT%H:%MZ")
            message = f"the newest run was made at {said}, too long ago to show"
            return {"data": None, "fetched_at": None, "stale": False, "message": message}
    return result
