"""The whole run, end to end, against canned responses."""

import json
import os
from datetime import timedelta

import pytest
from conftest import AT_NOW, FIRST_CANNED, NOW, fake_get

from breamfish import refresh

DOWN = RuntimeError("connection refused")
SENTINEL = b'{"schema": 1, "note": "the last good file"}\n'


@pytest.fixture
def responses(forecast_json, marine_json, tide_csv) -> dict:
    return {"/v1/forecast": forecast_json, "/v1/marine": marine_json, "tide-tables": tide_csv}


def read(data_dir, name):
    return json.loads((data_dir / "published" / name).read_text())


def test_run_publishes_conditions_and_status(tmp_path, responses, capsys):
    calls = []

    code = refresh.run(tmp_path, fake_get(responses, calls), now=NOW)

    assert code == 0
    assert len(calls) == 3  # one forecast, one marine, one tide file
    assert sorted(os.listdir(tmp_path / "published")) == ["conditions.json", "status.json"]

    conditions = read(tmp_path, "conditions.json")
    assert conditions["schema"] == 1
    assert conditions["generated_at"] == "2026-11-26T04:05:12Z"
    assert conditions["timezone"] == "Pacific/Auckland"
    assert len(conditions["hours"]) == 192

    entrance = conditions["zones"][0]
    assert entrance["weather_cell"] == [-35.887524, 174.53488]
    assert entrance["marine_cell"] == [-35.875, 174.62502]
    # The window starts at local midnight, 13 hours before the canned forecast does.
    after = FIRST_CANNED + 12  # the canned forecast is only 12 hours long
    assert entrance["wind_kn"][:FIRST_CANNED] == [None] * FIRST_CANNED
    assert entrance["wind_kn"][AT_NOW:after] == [8.6, 9.0, 9.6, 9.2, 8.5, 7.7, 7.6, 7.5]
    assert entrance["wind_kn"][after:] == [None] * (192 - after)
    assert entrance["wave_m"][AT_NOW] == 0.76
    assert entrance["comfort"]["boat"][AT_NOW:after] == [3] * 8
    assert entrance["comfort"]["boat"][after] == 0
    assert entrance["limit"]["boat"][after] == "no_data"
    for zone in conditions["zones"]:
        for style in ("boat", "kayak", "shore"):
            assert set(zone["comfort"][style]) <= {0, 1, 2, 3}
    assert conditions["tide"]["events"][0]["t"] == "2026-11-25T07:51Z"
    assert None not in conditions["tide"]["height"]
    assert len(conditions["sun"]) == 8

    status = read(tmp_path, "status.json")
    assert status["generated_at"] == "2026-11-26T04:05:12Z"
    assert status["ok"] is True
    assert [source["id"] for source in status["sources"]] == [
        "openmeteo_forecast",
        "openmeteo_marine",
        "linz_tides",
    ]
    for source in status["sources"]:
        assert source["ok"] is True
        assert source["stale"] is False
        assert source["fetched_at"] == "2026-11-26T04:05Z"
        assert source["message"] == ""

    log_lines = capsys.readouterr().err.splitlines()
    assert log_lines == [
        "openmeteo_forecast: ok, fetched 2026-11-26T04:05Z",
        "openmeteo_marine: ok, fetched 2026-11-26T04:05Z",
        "linz_tides: ok, fetched 2026-11-26T04:05Z",
    ]


def test_raw_responses_are_cached_with_fetch_times(tmp_path, responses, forecast_json):
    refresh.run(tmp_path, fake_get(responses), now=NOW)

    cache = tmp_path / "cache"
    assert sorted(os.listdir(cache)) == [
        "linz_marsden_point_2026.csv",
        "linz_marsden_point_2026.csv.meta.json",
        "openmeteo_forecast.json",
        "openmeteo_forecast.json.meta.json",
        "openmeteo_marine.json",
        "openmeteo_marine.json.meta.json",
    ]
    assert (cache / "openmeteo_forecast.json").read_bytes() == forecast_json
    meta = json.loads((cache / "openmeteo_forecast.json.meta.json").read_text())
    assert meta["fetched_at"] == "2026-11-26T04:05:12Z"


def test_no_forecast_and_no_cache_leaves_conditions_alone(tmp_path, responses, capsys):
    published = tmp_path / "published"
    published.mkdir()
    (published / "conditions.json").write_bytes(SENTINEL)

    code = refresh.run(tmp_path, fake_get(responses | {"/v1/forecast": DOWN}), now=NOW)

    assert code == 1
    assert (published / "conditions.json").read_bytes() == SENTINEL
    status = read(tmp_path, "status.json")  # still written, and says what is wrong
    assert status["ok"] is False
    forecast, marine, tide = status["sources"]
    assert forecast["ok"] is False
    assert forecast["fetched_at"] is None
    assert forecast["message"] == "fetch failed (RuntimeError: connection refused)"
    assert marine["ok"] is True
    assert tide["ok"] is True
    assert "openmeteo_forecast: FAILED" in capsys.readouterr().err


def test_forecast_outage_is_covered_by_the_cached_copy(tmp_path, responses):
    refresh.run(tmp_path, fake_get(responses), now=NOW)
    calls = []
    outage = fake_get(responses | {"/v1/forecast": DOWN, "/v1/marine": DOWN}, calls)

    code = refresh.run(tmp_path, outage, now=NOW + timedelta(hours=1))

    assert code == 0
    assert not any("tide-tables" in url for url in calls)  # fetched an hour ago: not again
    conditions = read(tmp_path, "conditions.json")
    assert conditions["generated_at"] == "2026-11-26T05:05:12Z"
    assert conditions["hours"][0] == "2026-11-25T11:00Z"  # still the same local day
    assert conditions["zones"][0]["wind_kn"][AT_NOW + 1] == 9.0  # the 05:00 value
    status = read(tmp_path, "status.json")
    assert status["ok"] is True
    for source in status["sources"][:2]:
        assert source["ok"] is True
        assert source["stale"] is True
        assert source["fetched_at"] == "2026-11-26T04:05Z"
        assert "connection refused" in source["message"]
    assert status["sources"][2]["stale"] is False


def test_cached_forecast_older_than_12_hours_is_not_published(tmp_path, responses):
    refresh.run(tmp_path, fake_get(responses), now=NOW)
    before = (tmp_path / "published" / "conditions.json").read_bytes()

    later = NOW + timedelta(hours=13)
    code = refresh.run(tmp_path, fake_get(responses | {"/v1/forecast": DOWN}), now=later)

    assert code == 1
    assert (tmp_path / "published" / "conditions.json").read_bytes() == before
    assert read(tmp_path, "status.json")["sources"][0]["ok"] is False


def test_a_forecast_with_nothing_in_the_window_is_not_published(tmp_path, responses):
    # Two days on, every hour of the canned forecast is in the past.
    code = refresh.run(tmp_path, fake_get(responses), now=NOW + timedelta(days=2))

    assert code == 1
    assert not (tmp_path / "published" / "conditions.json").exists()
    forecast = read(tmp_path, "status.json")["sources"][0]
    assert forecast["ok"] is False
    assert forecast["message"] == "no wind values for the next seven days"


def test_a_bad_forecast_response_counts_as_a_failed_fetch(tmp_path, responses):
    error_body = b'{"error": true, "reason": "Too many requests"}'

    code = refresh.run(tmp_path, fake_get(responses | {"/v1/forecast": error_body}), now=NOW)

    assert code == 1
    message = read(tmp_path, "status.json")["sources"][0]["message"]
    assert message == "fetch failed (ValueError: Too many requests)"


def test_marine_down_still_publishes_with_null_waves(tmp_path, responses):
    code = refresh.run(tmp_path, fake_get(responses | {"/v1/marine": DOWN}), now=NOW)

    assert code == 0
    entrance = read(tmp_path, "conditions.json")["zones"][0]
    assert entrance["marine_cell"] is None
    assert entrance["wave_m"] == [None] * 192
    assert entrance["sst_c"] == [None] * 192
    assert entrance["comfort"]["boat"][AT_NOW] == 3  # rated on wind and gust alone
    status = read(tmp_path, "status.json")
    assert status["ok"] is False
    assert [source["ok"] for source in status["sources"]] == [True, False, True]


def test_tides_down_still_publishes_with_a_null_tide(tmp_path, responses):
    code = refresh.run(tmp_path, fake_get(responses | {"tide-tables": DOWN}), now=NOW)

    assert code == 0
    tide = read(tmp_path, "conditions.json")["tide"]
    assert tide["events"] == []
    assert tide["height"] == [None] * 192
    assert tide["rate"] == [None] * 192
    status = read(tmp_path, "status.json")
    assert [source["ok"] for source in status["sources"]] == [True, True, False]
    assert status["sources"][2]["message"].startswith("2026: fetch failed")
