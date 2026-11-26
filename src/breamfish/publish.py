"""Build the two published documents and write files so readers never see half of one."""

import json
import os
from datetime import UTC, timedelta
from pathlib import Path

from breamfish import conditions, config, sun, tides


def iso_minute(t) -> str:
    return t.strftime("%Y-%m-%dT%H:%MZ")


def iso_second(t) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def rounded(value, places: int):
    if value is None:
        return None
    if places == 0:
        return round(value)
    return round(value, places) + 0.0  # the + 0.0 turns -0.0 into 0.0


def window(now) -> list:
    """The hours conditions.json covers, in UTC, starting at local midnight today.

    New Zealand's offset from UTC is always a whole number of hours, so local midnight
    falls exactly on a UTC hour.
    """
    local_midnight = now.astimezone(config.NZ).replace(hour=0, minute=0, second=0, microsecond=0)
    start = local_midnight.astimezone(UTC)
    return [start + timedelta(hours=n) for n in range(config.HOURS)]


def write_atomic(path: Path, data: bytes) -> None:
    """Replace path with data in one step: a reader sees the old file or the new one.

    The temporary file is opened the ordinary way, not with tempfile, so that it gets
    the usual permissions (0644 under the default umask) and the web server can read
    the result. tempfile would make it 0600.
    """
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def write_json(path: Path, document: dict) -> None:
    # allow_nan=False: NaN is not valid JSON and a browser would reject the whole file.
    # It raises before anything is written, so the published file stays as it was.
    text = json.dumps(document, separators=(",", ":"), allow_nan=False)
    write_atomic(path, (text + "\n").encode())


def build_zone(zone: dict, weather: dict, marine: dict | None, hours: list, tide_rate: list):
    """One entry of "zones". weather and marine are this zone's parsed Open-Meteo points.

    Values are matched to hours by timestamp, so a missing hour becomes null and never
    shifts the ones after it.
    """
    out = {
        "id": zone["id"],
        "name": zone["name"],
        "lat": zone["lat"],
        "lon": zone["lon"],
        "weather_cell": weather["cell"],
        "marine_cell": marine["cell"] if marine else None,
    }
    for key, variable, places in config.WEATHER_FIELDS:
        out[key] = [rounded(weather[variable].get(t), places) for t in hours]
    for key, variable, places in config.MARINE_FIELDS:
        series = marine[variable] if marine else {}
        out[key] = [rounded(series.get(t), places) for t in hours]

    # Rated on the rounded values, so the class always agrees with the numbers shown.
    rated = ("wind_kn", "gust_kn", "wave_m", "rain_mm", "wind_dir")
    per_hour = [
        {"tide_rate": tide_rate[n], **{key: out[key][n] for key in rated}}
        for n in range(len(hours))
    ]
    out["comfort"] = {}
    out["limit"] = {}
    for style in config.STYLES:
        ratings = [conditions.rate(style, zone, hour) for hour in per_hour]
        out["comfort"][style] = [level for level, _ in ratings]
        out["limit"][style] = [limit for _, limit in ratings]
    return out


def build_sun(hours: list) -> list[dict]:
    """The "sun" list: one entry per local date, times to the nearest minute."""
    days = []
    for day in sun.sun_times(hours[0], hours[-1]):
        entry = {"date": day["date"]}
        for name in ("dawn", "sunrise", "sunset", "dusk"):
            entry[name] = iso_minute(day[name] + timedelta(seconds=30))
        days.append(entry)
    return days


def build_conditions(now, forecast: list, marine: list | None, tide_events: list | None) -> dict:
    """The conditions.json document.

    forecast and marine hold one parsed point per zone, in config.ZONES order. marine
    and tide_events may be None when that source is down; those parts come out as nulls.
    """
    hours = window(now)
    tide_events = tides.events_around(tide_events or [], hours[0], hours[-1])
    tide_rate = [rounded(tides.rate_at(tide_events, t), 2) for t in hours]

    return {
        "schema": 1,
        "generated_at": iso_second(now),
        "timezone": config.TIMEZONE,
        "hours": [iso_minute(t) for t in hours],
        "tide": {
            "port": config.TIDE_PORT,
            "datum": config.TIDE_DATUM,
            "events": [
                {"t": iso_minute(e["t"]), "type": e["type"], "h": e["h"]} for e in tide_events
            ],
            "height": [rounded(tides.height_at(tide_events, t), 2) for t in hours],
            "rate": tide_rate,
        },
        "sun": build_sun(hours),
        "zones": [
            build_zone(zone, forecast[i], marine[i] if marine else None, hours, tide_rate)
            for i, zone in enumerate(config.ZONES)
        ],
        "thresholds": {
            "styles": config.THRESHOLDS,
            "modifiers": config.MODIFIERS,
            "zones": {
                zone["id"]: {
                    "offshore_from": zone["offshore_from"],
                    "onshore_from": zone["onshore_from"],
                    "ebb_hazard": zone["ebb_hazard"],
                }
                for zone in config.ZONES
            },
        },
    }


def build_status(now, sources: list) -> dict:
    """The status.json document. sources is a list of (id, name, fetch result)."""
    entries = [
        {
            "id": source_id,
            "name": name,
            "ok": result["data"] is not None,
            "stale": result["stale"],
            "fetched_at": iso_minute(result["fetched_at"]) if result["fetched_at"] else None,
            "message": result["message"],
        }
        for source_id, name, result in sources
    ]
    return {
        "generated_at": iso_second(now),
        "ok": all(entry["ok"] for entry in entries),
        "sources": entries,
    }
