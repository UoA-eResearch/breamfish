"""The published byte grids and contours."""

import gzip

import numpy as np
import pytest

from seabed import grid, publish


def test_depth_survives_the_round_trip_to_a_tenth_of_a_metre():
    values = np.full(grid.SHAPE, np.nan)
    values[0, 0:5] = [-2.7, 0.0, 0.04, 23.456, 118.0]
    stored = publish.encode(values, publish.DEPTH)
    assert stored.dtype == np.uint16
    assert stored[1, 1] == 0  # no data
    assert stored[0, 1] == 100  # chart datum itself: (0 - -10) / 0.1
    back = publish.decode(stored, publish.DEPTH)
    assert np.allclose(back[0, 0:5], [-2.7, 0.0, 0.0, 23.5, 118.0])
    assert np.isnan(back[1, 1])


def test_values_that_do_not_fit_are_clipped_not_wrapped():
    values = np.full(grid.SHAPE, np.nan)
    values[0, 0:3] = [0.0, 30.0, 80.0]
    slope = publish.decode(publish.encode(values, publish.SLOPE), publish.SLOPE)
    assert list(slope[0, 0:3]) == [0.0, 30.0, 63.5]
    rough = publish.decode(publish.encode(values, publish.ROUGHNESS), publish.ROUGHNESS)
    assert rough[0, 0] == 0.0 and rough[0, 1] == pytest.approx(5.08)
    # A real zero is stored as 1, never as the no-data 0.
    assert publish.encode(values, publish.SLOPE)[0, 0] == 1


def test_files_are_gzip_of_little_endian_rows_and_the_same_every_time():
    stored = np.arange(grid.NROWS * grid.NCOLS, dtype=np.uint16).reshape(grid.SHAPE)
    data = publish.to_bytes(stored)
    assert data == publish.to_bytes(stored)  # no timestamp inside
    raw = gzip.decompress(data)
    assert len(raw) == grid.NROWS * grid.NCOLS * 2
    assert raw[2:4] == b"\x01\x00"  # the second cell of the first row, low byte first
    assert (publish.from_bytes(data, "uint16") == stored).all()
    with pytest.raises(ValueError):
        publish.to_bytes(stored[:10])


def test_a_predicted_grid_comes_back_exactly_and_packs_smaller():
    shape = (40, 60)
    rows, cols = np.mgrid[0 : shape[0], 0 : shape[1]]
    slope = (200 + 3 * rows + 7 * cols).astype(np.uint16)  # a tilted seabed
    slope[10:15, 20:30] = 0  # a gap
    slope[0, 0], slope[0, 1], slope[1, 0] = 65535, 0, 65535  # the widest steps there are
    data = publish.to_bytes_predicted(slope, shape)
    assert data == publish.to_bytes_predicted(slope, shape)
    assert (publish.from_bytes_predicted(data, shape) == slope).all()
    assert len(data) < len(publish.to_bytes(slope, shape))
    with pytest.raises(ValueError):
        publish.to_bytes_predicted(slope.astype(np.uint8), shape)


def test_contours_can_be_drawn_from_a_finer_grid():
    fine_shape = grid.fine_shape(20)
    rows, cols = np.mgrid[0 : fine_shape[0], 0 : fine_shape[1]]
    ramp = cols * 20 / 1000.0  # one metre deeper every kilometre east
    result = publish.contours(
        ramp, (10,), to_lonlat=lambda e, n: (e, n), tolerance_m=5, sigma_cells=0
    )
    (line,) = result["features"]
    eastings = np.array(line["geometry"]["coordinates"])[:, 0]
    # Ten metres deep is ten kilometres east of the west edge, less half a 20 m cell.
    assert eastings == pytest.approx(grid.WEST_E + 10_000 + 10, abs=1)


def test_smoothing_keeps_gaps_as_gaps():
    values = np.full(grid.SHAPE, 10.0)
    values[5, 5] = np.nan
    values[50, 50] = 30.0
    smoothed = publish.smooth(values)
    assert np.isnan(smoothed[5, 5])
    assert smoothed[5, 6] == pytest.approx(10.0)  # the gap does not drag its neighbours
    assert 10 < smoothed[50, 50] < 30


def test_simplify_drops_only_vertices_near_the_line():
    line = np.array([[0, 0], [100, 2], [200, 0], [300, 80], [400, 0]], dtype=float)
    assert publish.simplify(line, 15).tolist() == [[0, 0], [200, 0], [300, 80], [400, 0]]


def test_contours_of_a_bowl_are_rings_at_the_asked_levels():
    cell_e, cell_n = grid.centres()
    centre_e, centre_n = cell_e.mean(), cell_n.mean()
    distance_km = np.hypot(cell_e - centre_e, cell_n - centre_n) / 1000
    bowl = np.clip(30 - 3 * distance_km, 0, None)  # 30 m deep in the middle, shoaling outwards
    bowl[distance_km > 9.5] = np.nan
    result = publish.contours(bowl, (10, 20, 50), to_lonlat=lambda e, n: (e / 1e4, n / 1e5))
    levels = sorted(f["properties"]["depth"] for f in result["features"])
    assert levels == [10, 20]  # nothing is 50 m deep
    ring = next(f for f in result["features"] if f["properties"]["depth"] == 20)
    xy = np.array(ring["geometry"]["coordinates"]) * [1e4, 1e5]
    radius_km = np.hypot(xy[:, 0] - centre_e, xy[:, 1] - centre_n) / 1000
    assert radius_km == pytest.approx((30 - 20) / 3, abs=0.12)
