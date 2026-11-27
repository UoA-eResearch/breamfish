"""The optional fine wind from the cluster: reading its file, and the hourly run with it."""

import json
import os
from datetime import timedelta

import pytest
from conftest import AT_NOW, NOW, WIND_FIELD, fake_get

from breamfish import config, publish, refresh
from breamfish.sources import cluster_wind

ADDRESS = "https://store.example/v1/AUTH_x/results/wind/latest.json"
DOWN = RuntimeError("connection refused")
SENTINEL = b'{"schema": 1, "note": "the last good file"}\n'


def run_document(made=None, first=None, hours=6):
    """What the cluster publishes: a two by three lattice with a steady 12 kn westerly.

    Made three hours before the run time used in these tests, and starting at its hour.
    """
    made = made or NOW - timedelta(hours=3)
    start = (first or NOW).replace(minute=0, second=0, microsecond=0)
    return {
        "schema": 1,
        "generated_at": made.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cycle": "2026112600",
        "hours": [(start + timedelta(hours=n)).strftime("%Y-%m-%dT%H:%MZ") for n in range(hours)],
        "unit": "kn",
        "source": {
            "id": "cluster_wind",
            "cell_km": [2.2, 1.8],
            "model_km": 1.0,
            "model": "WRF 4.8.1",
        },
        "grid": {
            "nrows": 2,
            "ncols": 3,
            "lats": [-35.8, -35.82],
            "lons": [[174.5, 174.52, 174.54], [174.5, 174.52, 174.54]],
        },
        "u": [[12.0] * 6 for _ in range(hours)],
        "v": [[0.0] * 6 for _ in range(hours)],
    }


def body(**changes) -> bytes:
    return json.dumps(run_document() | changes).encode()


@pytest.fixture
def responses(forecast_json, marine_json, tide_csv, wind_field_json) -> dict:
    return {
        "store.example": body(),
        WIND_FIELD: wind_field_json,
        "/v1/forecast": forecast_json,
        "/v1/marine": marine_json,
        "tide-tables": tide_csv,
    }


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv(config.FINE_WIND_ENV, ADDRESS)


def read(data_dir, name):
    return json.loads((data_dir / "published" / name).read_text())


# --- reading the cluster's file -----------------------------------------------------


def test_parse_keeps_the_grid_the_hours_and_what_made_them():
    run = cluster_wind.parse(body())

    assert run["cycle"] == "2026112600"
    assert run["hours"][0] == NOW.replace(minute=0, second=0, microsecond=0)
    assert len(run["hours"]) == 6
    assert run["grid"]["nrows"] == 2
    assert run["u"][0] == [12.0] * 6
    assert (run["cell_km"], run["model_km"], run["model"]) == ([2.2, 1.8], 1.0, "WRF 4.8.1")


@pytest.mark.parametrize(
    ("changes", "complaint"),
    [
        ({"schema": 2}, "schema 1"),
        ({"unit": "m/s"}, "knots"),
        ({"u": [[12.0] * 6] * 5}, "one entry for each hour"),
        ({"u": [[12.0] * 5] * 6}, "does not match the grid"),
        ({"v": [[0.0, 0.0, 0.0, 0.0, 0.0, 999.0]] * 6}, "cannot be a wind"),
        ({"v": [[0.0, 0.0, 0.0, 0.0, 0.0, "calm"]] * 6}, "cannot be a wind"),
        (
            {"hours": ["2026-11-26T05:00Z", "2026-11-26T04:00Z"] + ["2026-11-26T06:00Z"] * 4},
            "out of order",
        ),
    ],
)
def test_parse_refuses_a_file_the_map_could_not_draw_honestly(changes, complaint):
    with pytest.raises(ValueError, match=complaint):
        cluster_wind.parse(body(**changes))


def test_parse_refuses_a_grid_that_does_not_run_north_to_south_and_west_to_east():
    upside_down = run_document()["grid"] | {"lats": [-35.82, -35.8]}
    with pytest.raises(ValueError, match="north to south"):
        cluster_wind.parse(body(grid=upside_down))


def test_an_hour_with_no_frame_is_allowed():
    run = cluster_wind.parse(body(u=[None] + [[12.0] * 6] * 5))

    assert run["u"][0] is None


# --- the hourly run -----------------------------------------------------------------


def test_with_no_address_the_source_does_not_exist(tmp_path, responses, monkeypatch):
    monkeypatch.delenv(config.FINE_WIND_ENV, raising=False)
    calls = []

    code = refresh.run(tmp_path, fake_get(responses, calls), now=NOW)

    assert code == 0
    assert len(calls) == 4  # nothing asked of the cluster's address
    assert "wind_fine.json" not in os.listdir(tmp_path / "published")
    status = read(tmp_path, "status.json")
    assert [source["id"] for source in status["sources"]][-1] == "openmeteo_wind_field"
    assert "optional" not in json.dumps(status)


def test_with_an_address_the_run_is_published_on_the_sites_own_hours(
    tmp_path, responses, configured
):
    code = refresh.run(tmp_path, fake_get(responses), now=NOW)

    assert code == 0
    fine = read(tmp_path, "wind_fine.json")
    assert fine["hours"] == read(tmp_path, "conditions.json")["hours"]
    assert fine["unit"] == "kn"
    assert fine["source"] == {
        "id": "cluster_wind",
        "name": "Our own 1 km forecast",
        "cell_km": [2.2, 1.8],
        "model_km": 1.0,
        "model": "WRF 4.8.1",
        "cycle": "2026112600",
        "run_at": "2026-11-26T01:05Z",
    }
    assert fine["grid"]["lons"][1] == [174.5, 174.52, 174.54]
    # The run starts at the hour of this refresh and is six hours long.
    assert fine["u"][AT_NOW - 1] is None
    assert fine["u"][AT_NOW : AT_NOW + 6] == [[12.0] * 6] * 6
    assert fine["u"][AT_NOW + 6] is None
    assert len(fine["u"]) == len(fine["v"]) == 192

    status = read(tmp_path, "status.json")
    assert status["ok"] is True
    last = status["sources"][-1]
    assert (last["id"], last["ok"], last["optional"]) == ("cluster_wind", True, True)
    assert all("optional" not in source for source in status["sources"][:-1])


def test_the_cluster_being_down_is_reported_and_is_not_the_sites_trouble(
    tmp_path, responses, configured, capsys
):
    published = tmp_path / "published"
    published.mkdir()
    (published / "wind_fine.json").write_bytes(SENTINEL)

    code = refresh.run(tmp_path, fake_get(responses | {"store.example": DOWN}), now=NOW)

    assert code == 0
    assert (published / "wind_fine.json").read_bytes() == SENTINEL
    assert read(tmp_path, "wind.json")["u"][AT_NOW] is not None  # the public forecast is untouched
    status = read(tmp_path, "status.json")
    assert status["ok"] is True  # an optional source does not count
    last = status["sources"][-1]
    assert (last["id"], last["ok"], last["optional"]) == ("cluster_wind", False, True)
    assert "connection refused" in last["message"]
    assert "wind_fine.json left as it was" in capsys.readouterr().err


def test_a_run_made_too_long_ago_is_not_shown_however_freshly_fetched(
    tmp_path, responses, configured
):
    old = json.dumps(run_document(made=NOW - timedelta(hours=40))).encode()

    refresh.run(tmp_path, fake_get(responses | {"store.example": old}), now=NOW)

    assert "wind_fine.json" not in os.listdir(tmp_path / "published")
    last = read(tmp_path, "status.json")["sources"][-1]
    assert last["ok"] is False
    assert last["message"] == "the newest run was made at 2026-11-24T12:05Z, too long ago to show"


def test_a_run_that_reaches_none_of_the_sites_hours_is_not_published(
    tmp_path, responses, configured
):
    past = json.dumps(run_document(first=NOW - timedelta(days=3))).encode()

    refresh.run(tmp_path, fake_get(responses | {"store.example": past}), now=NOW)

    assert "wind_fine.json" not in os.listdir(tmp_path / "published")
    assert read(tmp_path, "status.json")["sources"][-1]["message"] == (
        "the newest run holds no hour of the next seven days"
    )


def test_a_broken_file_from_the_cluster_falls_back_to_the_last_good_one(
    tmp_path, responses, configured
):
    refresh.run(tmp_path, fake_get(responses), now=NOW)

    later = NOW + timedelta(hours=1)
    refresh.run(
        tmp_path, fake_get(responses | {"store.example": b'{"schema": 1, "unit"'}), now=later
    )

    fine = read(tmp_path, "wind_fine.json")
    assert fine["generated_at"] == "2026-11-26T05:05:12Z"  # republished from the cached copy
    last = read(tmp_path, "status.json")["sources"][-1]
    assert (last["ok"], last["stale"]) == (True, True)


def test_build_status_counts_only_what_the_site_needs():
    good = {"data": {}, "fetched_at": NOW, "stale": False, "message": ""}
    bad = {"data": None, "fetched_at": None, "stale": False, "message": "down"}

    status = publish.build_status(NOW, [("a", "A", good), ("b", "B", bad)], optional=("b",))

    assert status["ok"] is True
    assert status["sources"][1]["optional"] is True
    assert publish.build_status(NOW, [("a", "A", good), ("b", "B", bad)])["ok"] is False
