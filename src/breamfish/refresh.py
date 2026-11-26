"""The hourly run: fetch the sources, build the documents, publish them."""

import sys
from datetime import UTC, datetime
from pathlib import Path

from breamfish import publish
from breamfish.sources import linz_tides, openmeteo


def log(text: str) -> None:
    print(text, file=sys.stderr)


def summary(source_id: str, result: dict) -> str:
    """The one log line for a source."""
    if result["data"] is None:
        return f"{source_id}: FAILED, {result['message']}"
    state = "STALE" if result["stale"] else "ok"
    line = f"{source_id}: {state}, fetched {publish.iso_minute(result['fetched_at'])}"
    return f"{line}, {result['message']}" if result["message"] else line


def has_wind(forecast: list, hours: list) -> bool:
    """Does the forecast hold at least one wind value inside the window?"""
    return any(point["wind_speed_10m"].get(t) is not None for point in forecast for t in hours)


def field_has_wind(field: dict, hours: list) -> bool:
    """Does the wind field hold at least one wind value inside the window?"""
    return has_wind(field["points"], hours)


def run(data_dir: Path, get, now=None) -> int:
    """Refresh the published files and return the process exit code.

    get(url, params) fetches a URL and returns the body as bytes; tests pass a fake.
    Exit code 1 means there was no usable forecast, so conditions.json was left as it
    was. A missing marine or tide source only leaves nulls and still exits 0. So does a
    missing wind field: wind.json is left as it was and the map goes without it.
    """
    now = now or datetime.now(UTC)
    hours = publish.window(now)
    cache_dir = data_dir / "cache"
    published_dir = data_dir / "published"
    cache_dir.mkdir(parents=True, exist_ok=True)
    published_dir.mkdir(parents=True, exist_ok=True)

    forecast = openmeteo.fetch_forecast(get, cache_dir, now)
    marine = openmeteo.fetch_marine(get, cache_dir, now)
    tide = linz_tides.fetch_events(get, cache_dir, hours[0], hours[-1], now)
    field = openmeteo.fetch_wind_field(get, cache_dir, now)

    if forecast["data"] is not None and not has_wind(forecast["data"], hours):
        message = "no wind values for the next seven days"
        forecast = {"data": None, "fetched_at": None, "stale": False, "message": message}
    if field["data"] is not None and not field_has_wind(field["data"], hours):
        message = "no wind values for the next seven days"
        field = {"data": None, "fetched_at": None, "stale": False, "message": message}

    sources = [
        ("openmeteo_forecast", "Open-Meteo forecast", forecast),
        ("openmeteo_marine", "Open-Meteo marine", marine),
        ("linz_tides", "LINZ tide predictions", tide),
        ("openmeteo_wind_field", "Open-Meteo wind field", field),
    ]
    for source_id, _, result in sources:
        log(summary(source_id, result))

    # Never replace a good conditions.json with an empty one.
    if forecast["data"] is not None:
        document = publish.build_conditions(now, forecast["data"], marine["data"], tide["data"])
        publish.write_json(published_dir / "conditions.json", document)
    else:
        log("conditions.json left as it was: no usable forecast")
    # The same for the wind on the map. The site checks status.json before it draws it.
    if field["data"] is not None:
        document = publish.build_wind(now, field["data"], field["fetched_at"])
        publish.write_json(published_dir / "wind.json", document)
    else:
        log("wind.json left as it was: no usable wind field")
    publish.write_json(published_dir / "status.json", publish.build_status(now, sources))
    return 0 if forecast["data"] is not None else 1
