"""Open-Meteo forecast and marine APIs: one request each, covering every zone."""

import json
from datetime import UTC, datetime
from functools import partial

from breamfish import config
from breamfish.sources.fetch import fetch_cached


def request_params(point: str, fields: list) -> dict:
    """Query parameters asking for fields at every zone's "weather" or "marine" point."""
    return {
        "latitude": ",".join(str(zone[point][0]) for zone in config.ZONES),
        "longitude": ",".join(str(zone[point][1]) for zone in config.ZONES),
        "hourly": ",".join(variable for _, variable, _ in fields),
        "timezone": "UTC",
        "past_days": config.PAST_DAYS,
        "forecast_days": config.FORECAST_DAYS,
        "cell_selection": config.CELL_SELECTION,
    }


def parse_points(body: bytes, fields: list) -> list[dict]:
    """Turn a multi-point response into one dict per zone, in config.ZONES order.

    Each dict is {"cell": [lat, lon], "<variable>": {time: value, ...}, ...}. cell is
    the grid point Open-Meteo actually used. Times are UTC datetimes, so a series can
    be matched to the published hours by timestamp. Raises if the response is not what
    was asked for.
    """
    points = json.loads(body)
    if isinstance(points, dict):  # an error report: {"error": true, "reason": "..."}
        raise ValueError(points.get("reason", "expected a list with one entry per zone"))
    if len(points) != len(config.ZONES):
        raise ValueError(f"expected {len(config.ZONES)} points, got {len(points)}")

    parsed = []
    for point in points:
        if point.get("utc_offset_seconds", 0) != 0:
            raise ValueError("times are not in UTC")
        hourly = point["hourly"]
        # Times look like 2026-11-26T00:00 with no suffix; they are UTC because we ask for it.
        times = [datetime.fromisoformat(t).replace(tzinfo=UTC) for t in hourly["time"]]
        if not times:
            raise ValueError("no hours in the response")
        entry = {"cell": [point["latitude"], point["longitude"]]}
        for _, variable, _ in fields:
            entry[variable] = dict(zip(times, hourly[variable], strict=True))
        parsed.append(entry)
    return parsed


def fetch_forecast(get, cache_dir, now) -> dict:
    """Wind, rain, cloud and air temperature. Returns a fetch_cached result."""
    params = request_params("weather", config.WEATHER_FIELDS) | {"wind_speed_unit": "kn"}
    return fetch_cached(
        get,
        cache_dir,
        "openmeteo_forecast.json",
        config.FORECAST_URL,
        params,
        parse=partial(parse_points, fields=config.WEATHER_FIELDS),
        now=now,
        max_age=config.OPENMETEO_MAX_AGE,
    )


def fetch_marine(get, cache_dir, now) -> dict:
    """Waves, swell and sea temperature. Returns a fetch_cached result."""
    return fetch_cached(
        get,
        cache_dir,
        "openmeteo_marine.json",
        config.MARINE_URL,
        request_params("marine", config.MARINE_FIELDS),
        parse=partial(parse_points, fields=config.MARINE_FIELDS),
        now=now,
        max_age=config.OPENMETEO_MAX_AGE,
    )
