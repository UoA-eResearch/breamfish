import json
import os
import stat
from datetime import UTC, datetime, timedelta

import pytest
from conftest import NOW

from breamfish import config, publish, tides
from breamfish.sources import linz_tides

HOURS = publish.window(NOW)


def weather_point(hours, **overrides):
    """A parsed forecast point holding the same steady weather for every hour given."""
    values = {
        "wind_speed_10m": 5.0,
        "wind_gusts_10m": 8.0,
        "wind_direction_10m": 200,
        "precipitation": 0.0,
        "cloud_cover": 50,
        "temperature_2m": 18.0,
    } | overrides
    point = {"cell": [-35.9, 174.5]}
    for variable, value in values.items():
        point[variable] = dict.fromkeys(hours, value)
    return point


def steady_forecast(hours=HOURS):
    return [weather_point(hours) for _ in config.ZONES]


# --- atomic writes ------------------------------------------------------------------


def test_write_atomic_replaces_the_file_and_leaves_no_temporary_file(tmp_path):
    target = tmp_path / "conditions.json"
    target.write_bytes(b"old")

    publish.write_atomic(target, b"new")

    assert target.read_bytes() == b"new"
    assert os.listdir(tmp_path) == ["conditions.json"]


def test_published_file_is_readable_by_the_web_server(tmp_path):
    previous_umask = os.umask(0o022)  # the usual default, and what systemd gives a service
    try:
        publish.write_atomic(tmp_path / "status.json", b"{}")
    finally:
        os.umask(previous_umask)
    assert stat.S_IMODE((tmp_path / "status.json").stat().st_mode) == 0o644


def test_a_document_that_is_not_valid_json_never_reaches_the_file(tmp_path):
    target = tmp_path / "conditions.json"
    target.write_bytes(b"good")

    with pytest.raises(ValueError):
        publish.write_json(target, {"wind_kn": [float("nan")]})

    assert target.read_bytes() == b"good"
    assert os.listdir(tmp_path) == ["conditions.json"]


def test_a_failed_write_keeps_the_old_file_and_cleans_up(tmp_path, monkeypatch):
    target = tmp_path / "conditions.json"
    target.write_bytes(b"good")

    def disk_full(fd):
        raise OSError("No space left on device")

    monkeypatch.setattr(os, "fsync", disk_full)
    with pytest.raises(OSError):
        publish.write_atomic(target, b"new")

    assert target.read_bytes() == b"good"
    assert os.listdir(tmp_path) == ["conditions.json"]


# --- conditions.json ----------------------------------------------------------------


def test_timestamps_are_utc_to_the_minute_with_seconds_only_on_generated_at():
    document = publish.build_conditions(NOW, steady_forecast(), None, None)

    assert document["generated_at"] == "2026-11-26T04:05:12Z"
    assert len(document["hours"]) == 192
    # Midnight on 26 November in New Zealand is 11:00 UTC on the 25th.
    assert document["hours"][:2] == ["2026-11-25T11:00Z", "2026-11-25T12:00Z"]
    assert document["hours"][-1] == "2026-12-03T10:00Z"


def test_series_are_matched_by_timestamp_and_a_gap_becomes_null():
    forecast = steady_forecast()
    del forecast[0]["wind_speed_10m"][HOURS[2]]  # the source skipped an hour
    forecast[0]["wind_speed_10m"][HOURS[3]] = 7.7

    zones = publish.build_conditions(NOW, forecast, None, None)["zones"]

    assert zones[0]["wind_kn"][:5] == [5.0, 5.0, None, 7.7, 5.0]  # nothing shifted along
    assert zones[0]["gust_kn"][2] == 8.0
    assert zones[0]["comfort"]["boat"][:4] == [3, 3, 0, 3]
    assert zones[0]["limit"]["boat"][:4] == ["ok", "ok", "no_data", "ok"]
    assert zones[1]["wind_kn"][2] == 5.0  # the other zones are untouched


def test_a_series_that_starts_before_the_window_is_not_matched_by_position():
    early = [HOURS[0] + timedelta(hours=n) for n in range(-4, 6)]
    forecast = steady_forecast(early)
    for n, t in enumerate(early):
        forecast[0]["temperature_2m"][t] = 10.0 + n

    zone = publish.build_conditions(NOW, forecast, None, None)["zones"][0]

    assert zone["air_c"][:7] == [14.0, 15.0, 16.0, 17.0, 18.0, 19.0, None]
    assert len(zone["air_c"]) == 192
    assert zone["comfort"]["shore"][5:7] == [3, 0]


def test_every_hourly_list_has_one_entry_per_hour():
    document = publish.build_conditions(NOW, steady_forecast(HOURS[:10]), None, None)

    assert len(document["tide"]["height"]) == len(document["tide"]["rate"]) == 192
    for zone in document["zones"]:
        for key in [key for key, _, _ in config.WEATHER_FIELDS + config.MARINE_FIELDS]:
            assert len(zone[key]) == 192, key
        for style in ("boat", "kayak", "shore"):
            assert len(zone["comfort"][style]) == len(zone["limit"][style]) == 192


def test_values_are_rounded_as_the_contract_says():
    forecast = [
        weather_point(
            HOURS,
            wind_speed_10m=5.04,
            wind_direction_10m=199.6,
            cloud_cover=49.5,
            temperature_2m=17.96,
        )
        for _ in config.ZONES
    ]
    marine = [
        {
            "cell": [-35.9, 174.6],
            "wave_height": dict.fromkeys(HOURS, 0.756),
            "wave_direction": dict.fromkeys(HOURS, 53.4),
            "wave_period": dict.fromkeys(HOURS, 7.95),
            "swell_wave_height": dict.fromkeys(HOURS, 0.584),
            "swell_wave_period": dict.fromkeys(HOURS, 8.26),
            "sea_surface_temperature": dict.fromkeys(HOURS, 19.44),
        }
        for _ in config.ZONES
    ]

    zone = publish.build_conditions(NOW, forecast, marine, None)["zones"][0]

    assert zone["wind_kn"][0] == 5.0
    assert zone["air_c"][0] == 18.0
    assert zone["wave_m"][0] == 0.76
    assert zone["swell_m"][0] == 0.58
    assert zone["swell_period_s"][0] == 8.3
    assert zone["sst_c"][0] == 19.4
    for key, expected in (("wind_dir", 200), ("cloud_pct", 50), ("wave_dir", 53)):
        assert zone[key][0] == expected
        assert isinstance(zone[key][0], int)
    assert zone["marine_cell"] == [-35.9, 174.6]


def test_zone_details_and_thresholds_are_published():
    document = publish.build_conditions(NOW, steady_forecast(), None, None)

    entrance = document["zones"][0]
    assert [zone["id"] for zone in document["zones"]] == ["entrance", "inner", "outer"]
    assert entrance["name"] == "Harbour entrance and Urquharts Bay"
    assert (entrance["lat"], entrance["lon"]) == (-35.845, 174.53)
    assert entrance["weather_cell"] == [-35.9, 174.5]
    assert entrance["marine_cell"] is None
    assert entrance["wave_m"] == [None] * 192

    thresholds = json.loads(json.dumps(document["thresholds"]))  # as the browser sees it
    assert thresholds["styles"]["kayak"]["fair"] == {"wind_kn": 12, "gust_kn": 17, "wave_m": 0.8}
    assert thresholds["modifiers"]["rain_mm"] == 4.0
    assert thresholds["zones"]["entrance"] == {
        "offshore_from": [300, 60],
        "onshore_from": [60, 160],
        "ebb_hazard": True,
    }
    assert thresholds["zones"]["outer"]["offshore_from"] is None


def test_tide_curve_and_events_cover_the_window(tide_csv):
    events = tides.label_high_low(linz_tides.parse_csv(tide_csv))

    tide = publish.build_conditions(NOW, steady_forecast(), None, events)["tide"]

    assert tide["port"] == "Marsden Point"
    assert tide["datum"] == "chart datum"
    # From the tide before local midnight on the 26th: high water at 20:51 NZDT...
    assert tide["events"][0] == {"t": "2026-11-25T07:51Z", "type": "high", "h": 2.7}
    assert tide["events"][1] == {"t": "2026-11-25T14:04Z", "type": "low", "h": 0.4}
    # ...to the one after 10:00 UTC on 3 December: high water at 04:24 NZDT on the 4th,
    # and no further.
    assert tide["events"][-2] == {"t": "2026-12-03T09:07Z", "type": "low", "h": 0.7}
    assert tide["events"][-1] == {"t": "2026-12-03T15:24Z", "type": "high", "h": 2.4}
    assert None not in tide["height"]
    assert None not in tide["rate"]
    assert tide["height"][0] == 1.53  # 189 minutes into a 373 minute fall from 2.7 to 0.4
    assert tide["rate"][0] == -0.58  # falling fast, about mid-tide
    assert max(tide["rate"]) > 0.5  # and rising at other times


def test_sun_times_are_published_to_the_minute():
    sun_days = publish.build_conditions(NOW, steady_forecast(), None, None)["sun"]

    assert [day["date"] for day in sun_days][:2] == ["2026-11-26", "2026-11-27"]
    assert len(sun_days) == 8
    first = sun_days[0]
    assert set(first) == {"date", "dawn", "sunrise", "sunset", "dusk"}
    for name in ("dawn", "sunrise", "sunset", "dusk"):
        parsed = datetime.strptime(first[name], "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)
        assert publish.iso_minute(parsed) == first[name]


# --- status.json --------------------------------------------------------------------


def test_status_lists_each_source():
    good = {"data": [1], "fetched_at": NOW, "stale": False, "message": ""}
    stale = {"data": [1], "fetched_at": NOW - timedelta(hours=3), "stale": True, "message": "x"}
    dead = {"data": None, "fetched_at": None, "stale": False, "message": "fetch failed"}

    status = publish.build_status(NOW, [("a", "Source A", good), ("b", "Source B", stale)])
    assert status == {
        "generated_at": "2026-11-26T04:05:12Z",
        "ok": True,  # stale is still usable
        "sources": [
            {
                "id": "a",
                "name": "Source A",
                "ok": True,
                "stale": False,
                "fetched_at": "2026-11-26T04:05Z",
                "message": "",
            },
            {
                "id": "b",
                "name": "Source B",
                "ok": True,
                "stale": True,
                "fetched_at": "2026-11-26T01:05Z",
                "message": "x",
            },
        ],
    }

    broken = publish.build_status(NOW, [("a", "Source A", good), ("c", "Source C", dead)])
    assert broken["ok"] is False
    assert broken["sources"][1]["ok"] is False
    assert broken["sources"][1]["fetched_at"] is None
