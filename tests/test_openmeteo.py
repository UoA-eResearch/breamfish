"""The Open-Meteo requests and what is made of the answers."""

import json

import pytest

from breamfish import config
from breamfish.sources import openmeteo


def test_lattice_points_run_row_by_row_from_the_north_west():
    points = openmeteo.lattice_points()

    assert len(points) == 48
    assert points[0] == (-35.7, 174.3)
    assert points[1] == (-35.7, 174.415)  # east along the row first
    assert points[6] == (-35.77, 174.3)  # then the next row south
    assert points[-1] == (-36.19, 174.875)


def test_the_wind_field_request_asks_for_the_model_cells_as_they_are():
    params = openmeteo.request_params(
        openmeteo.lattice_points(), config.WIND_FIELD_FIELDS, config.WIND_CELL_SELECTION
    )

    assert params["hourly"] == "wind_speed_10m,wind_direction_10m"
    assert params["cell_selection"] == "nearest"
    assert params["latitude"].count(",") == 47
    assert params["timezone"] == "UTC"


def test_parse_wind_field_keeps_each_row_of_cells_where_the_model_has_it(wind_field_json):
    field = openmeteo.parse_wind_field(wind_field_json)

    assert len(field["points"]) == 48
    assert len(field["lats"]) == 8
    assert field["lats"] == sorted(field["lats"], reverse=True)  # north to south
    for row in field["lons"]:
        assert len(row) == 6
        assert row == sorted(row)  # west to east
    # The cells do not line up from one row to the next.
    assert field["lons"][0][0] != field["lons"][7][0]
    assert field["points"][0]["cell"] == [field["lats"][0], field["lons"][0][0]]


def test_parse_wind_field_refuses_points_that_share_a_cell(wind_field_json):
    points = json.loads(wind_field_json)
    points[1]["longitude"] = points[0]["longitude"]

    with pytest.raises(ValueError, match="no longer lands on rows"):
        openmeteo.parse_wind_field(json.dumps(points).encode())


def test_parse_wind_field_refuses_rows_out_of_order(wind_field_json):
    points = json.loads(wind_field_json)
    points[:6], points[6:12] = points[6:12], points[:6]

    with pytest.raises(ValueError, match="no longer lands on rows"):
        openmeteo.parse_wind_field(json.dumps(points).encode())


def test_parse_wind_field_refuses_the_wrong_number_of_points(forecast_json):
    with pytest.raises(ValueError, match="expected 48 points, got 3"):
        openmeteo.parse_wind_field(forecast_json)
