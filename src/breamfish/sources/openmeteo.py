"""Open-Meteo forecast and marine APIs: one request each for the zones, one for the wind field."""

import json
from datetime import UTC, datetime
from functools import partial

from breamfish import config
from breamfish.sources.fetch import fetch_cached


def zone_points(point: str) -> list:
    """Every zone's "weather" or "marine" point, as (latitude, longitude)."""
    return [zone[point] for zone in config.ZONES]


def lattice_points() -> list:
    """The points of config.WIND_LATTICE, row by row from the north-west corner."""
    lattice = config.WIND_LATTICE
    return [
        (
            round(lattice["north"] - row * lattice["dlat"], 4),
            round(lattice["west"] + col * lattice["dlon"], 4),
        )
        for row in range(lattice["nrows"])
        for col in range(lattice["ncols"])
    ]


def request_params(points: list, fields: list, cell_selection: str) -> dict:
    """Query parameters asking for fields at each (latitude, longitude) point."""
    return {
        "latitude": ",".join(str(latitude) for latitude, _ in points),
        "longitude": ",".join(str(longitude) for _, longitude in points),
        "hourly": ",".join(variable for _, variable, _ in fields),
        "timezone": "UTC",
        "past_days": config.PAST_DAYS,
        "forecast_days": config.FORECAST_DAYS,
        "cell_selection": cell_selection,
    }


def parse_points(body: bytes, fields: list, count: int) -> list[dict]:
    """Turn a multi-point response into one dict per point, in the order asked for.

    Each dict is {"cell": [lat, lon], "<variable>": {time: value, ...}, ...}. cell is
    the grid point Open-Meteo actually used. Times are UTC datetimes, so a series can
    be matched to the published hours by timestamp. Raises if the response is not what
    was asked for.
    """
    points = json.loads(body)
    if isinstance(points, dict):  # an error report: {"error": true, "reason": "..."}
        raise ValueError(points.get("reason", "expected a list with one entry per point"))
    if len(points) != count:
        raise ValueError(f"expected {count} points, got {len(points)}")

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


def parse_wind_field(body: bytes) -> dict:
    """Turn the lattice response into {"lats", "lons", "points"}.

    lats has one latitude per row, north to south. lons has each row's longitudes, west
    to east: the model's cells do not line up from one row to the next, so every row
    keeps its own. points is parse_points's list, row by row.

    Raises if the answers are not rows of different cells. That means the weather model
    behind the API has changed and config.WIND_LATTICE must be laid out again.
    """
    lattice = config.WIND_LATTICE
    nrows, ncols = lattice["nrows"], lattice["ncols"]
    points = parse_points(body, config.WIND_FIELD_FIELDS, nrows * ncols)
    wrong = ValueError("the wind lattice no longer lands on rows of different model cells")

    lats, lons = [], []
    for row in range(nrows):
        cells = [point["cell"] for point in points[row * ncols : (row + 1) * ncols]]
        row_lats = [lat for lat, _ in cells]
        row_lons = [lon for _, lon in cells]
        if max(row_lats) - min(row_lats) > 0.01:
            raise wrong
        if any(east <= west for west, east in zip(row_lons, row_lons[1:], strict=False)):
            raise wrong
        if lats and row_lats[0] >= lats[-1]:
            raise wrong
        lats.append(row_lats[0])
        lons.append(row_lons)
    return {"lats": lats, "lons": lons, "points": points}


def fetch_forecast(get, cache_dir, now) -> dict:
    """Wind, rain, cloud and air temperature. Returns a fetch_cached result."""
    params = request_params(zone_points("weather"), config.WEATHER_FIELDS, config.CELL_SELECTION)
    return fetch_cached(
        get,
        cache_dir,
        "openmeteo_forecast.json",
        config.FORECAST_URL,
        params | {"wind_speed_unit": "kn"},
        parse=partial(parse_points, fields=config.WEATHER_FIELDS, count=len(config.ZONES)),
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
        request_params(zone_points("marine"), config.MARINE_FIELDS, config.CELL_SELECTION),
        parse=partial(parse_points, fields=config.MARINE_FIELDS, count=len(config.ZONES)),
        now=now,
        max_age=config.OPENMETEO_MAX_AGE,
    )


def fetch_wind_field(get, cache_dir, now) -> dict:
    """Wind speed and direction over the whole map. Returns a fetch_cached result.

    A request of its own, so that trouble with it never touches the zones' forecast.
    """
    params = request_params(lattice_points(), config.WIND_FIELD_FIELDS, config.WIND_CELL_SELECTION)
    return fetch_cached(
        get,
        cache_dir,
        "openmeteo_wind_field.json",
        config.FORECAST_URL,
        params | {"wind_speed_unit": "kn"},
        parse=parse_wind_field,
        now=now,
        max_age=config.OPENMETEO_MAX_AGE,
    )
