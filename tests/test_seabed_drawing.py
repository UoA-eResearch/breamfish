"""The 20 m drawing grids: the pieces. tests/test_seabed_build.py runs them on a whole scene."""

import numpy as np
import pytest

from seabed import bottom, depth, drawing, grid


def test_halving_takes_the_mean_of_what_is_there():
    fine = np.full(grid.fine_shape(10), np.nan)
    fine[0:2, 0:2] = [[4.0, 6.0], [np.nan, np.nan]]  # two of four
    fine[0:2, 2:4] = [[8.0, np.nan], [np.nan, np.nan]]  # one of four: not enough
    out = drawing.halve(fine)
    assert out.shape == drawing.SHAPE
    assert out[0, 0] == pytest.approx(5.0)
    assert np.isnan(out[0, 1])


def test_a_grid_drawn_between_centres_passes_through_them():
    cell_e, cell_n = grid.centres()
    tilt = (cell_e - grid.WEST_E) / 1000 + (grid.NORTH_N - cell_n) / 500
    out = drawing.between_centres(tilt)
    assert out.shape == drawing.SHAPE
    middle = out[2 :: drawing.FACTOR, 2 :: drawing.FACTOR]  # the 20 m cell on each centre
    assert middle[5:-5, 5:-5] == pytest.approx(tilt[5:-5, 5:-5], abs=1e-6)
    # And a tilted plane stays a plane in between.
    assert out[502, 503] - out[502, 502] == pytest.approx(0.02, abs=1e-6)


def test_gaps_are_filled_from_the_nearest_cell_before_drawing():
    values = np.full(grid.SHAPE, 12.0)
    values[:, 100:] = np.nan
    out = drawing.between_centres(values)
    assert not np.isnan(out).any()
    assert out[500, 1500] == pytest.approx(12.0)


def test_a_mark_is_drawn_as_a_dot():
    marks = np.zeros(grid.SHAPE, dtype=np.uint8)
    marks[3, 4] = bottom.ROCK
    out = drawing.dots(marks)
    block = out[15:20, 20:25]
    assert block.sum() == 21 * bottom.ROCK  # 25 cells less the four corners
    assert block[0, 0] == block[4, 4] == 0 and block[2, 2] == bottom.ROCK
    assert out.sum() == block.sum()


def scene():
    """LiDAR water west of fine column 1000, charted water to its east, land beyond 1500."""
    lidar = np.full(grid.fine_shape(10), np.nan, dtype=np.float32)
    lidar[:, 0:2000] = 5.0
    multibeam = np.full(drawing.SHAPE, np.nan, dtype=np.float32)
    charted_depth = np.full(drawing.SHAPE, 20.0)
    cell_source = np.full(grid.SHAPE, depth.CHART_RECENT.code, dtype=np.uint8)
    cell_source[:, 0:200] = depth.LIDAR.code
    cell_source[:, 300:] = 0
    land = np.zeros(drawing.SHAPE, dtype=bool)
    land[:, 1500:] = True
    charted = np.ones(drawing.SHAPE, dtype=bool)
    return lidar, multibeam, charted_depth, cell_source, land, charted


def test_charted_water_meets_a_survey_without_a_step():
    out, source = drawing.surface(*scene())
    row = 900
    assert out[row, 990] == pytest.approx(5.0, abs=1e-6) and source[row, 990] == depth.LIDAR.code
    assert source[row, 1000] == depth.CHART_RECENT.code
    # Hard against the survey it is still the survey's depth; a few cells on, the chart's.
    assert out[row, 1000] == pytest.approx(5.0, abs=0.5)
    assert out[row, 1020] == pytest.approx(20.0, abs=1e-6)
    steps = np.abs(np.diff(out[row, 990:1020]))
    assert steps.max() < 6  # 15 m is crossed over several cells, not in one


def test_a_hole_in_a_survey_is_filled_from_the_survey():
    lidar, *rest = scene()
    lidar[1000:1004, 600:604] = np.nan  # two 20 m cells square
    out, source = drawing.surface(lidar, *rest)
    assert out[500, 300] == pytest.approx(5.0, abs=1e-6)
    assert source[500, 300] == depth.LIDAR.code  # credited to its 100 m cell's source


def test_land_is_empty_but_for_a_marked_fringe():
    out, source = drawing.surface(*scene())
    row = 900
    assert source[row, 1499] == depth.CHART_RECENT.code
    fringe = source[row, 1500:1505]
    assert (fringe == depth.CHART_RECENT.code + drawing.PAST_SHORE).all()
    assert out[row, 1504] == pytest.approx(20.0, abs=1e-6)
    assert source[row, 1505] == 0 and np.isnan(out[row, 1505])


def test_where_there_is_no_chart_the_100_m_grid_decides_what_is_water():
    lidar, multibeam, charted_depth, cell_source, land, charted = scene()
    charted[:] = False
    out, source = drawing.surface(lidar, multibeam, charted_depth, cell_source, land, charted)
    assert source[900, 1400] == depth.CHART_RECENT.code  # a 100 m cell with a depth
    assert out[900, 1400] == pytest.approx(20.0, abs=1e-6)
    assert source[900, 1500 + int(drawing.BLEED_CELLS)] == 0  # 100 m cells with none


def test_bottom_type_is_classed_only_in_water_and_repeated_on_the_fringe():
    source = np.zeros(drawing.SHAPE, dtype=np.uint8)
    source[:, :1000] = depth.LIDAR.code
    source[:, 1000:1005] = depth.LIDAR.code + drawing.PAST_SHORE
    habitat = np.full(drawing.SHAPE, bottom.SAND, dtype=np.uint8)
    rock = np.zeros(drawing.SHAPE, dtype=np.uint8)
    rock[100:110, 990:1100] = bottom.ROCK
    none = np.zeros(grid.SHAPE, dtype=np.uint8)
    kind, kind_source = drawing.bottom_type(rock, none, none, habitat, source)
    assert (kind[50, 999], kind_source[50, 999]) == (bottom.SAND, bottom.HABITAT_MAP)
    assert (kind[105, 999], kind_source[105, 999]) == (bottom.ROCK, bottom.CHART_ROCK)
    assert kind[105, 1003] == bottom.ROCK and kind[50, 1003] == bottom.SAND  # the fringe
    assert kind[105, 1050] == bottom.UNKNOWN and kind_source[105, 1050] == bottom.NO_SOURCE
