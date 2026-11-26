"""Vertical datums, the order of trust in the merge, and slope and roughness."""

import numpy as np
import pytest

from seabed import depth, grid


def blank():
    return np.full(grid.SHAPE, np.nan)


# --- Datums ---------------------------------------------------------------------------


def test_chart_datum_offset_comes_from_the_marsden_point_benchmark():
    # Chart datum is 4.816 m below benchmark DJM9; DJM9 is 3.07 m in NZVD2016.
    assert pytest.approx(-1.746) == depth.CD_NZVD2016_M


def test_lidar_heights_become_depths_below_chart_datum():
    assert depth.depth_from_nzvd2016(depth.CD_NZVD2016_M) == pytest.approx(0.0)
    assert depth.depth_from_nzvd2016(-10.0) == pytest.approx(8.254)
    # The benchmark itself is 4.816 m above chart datum.
    assert depth.depth_from_nzvd2016(3.07) == pytest.approx(-4.816)


def test_the_datums_agree_about_mean_sea_level():
    # Mean sea level is 1.63 m above chart datum however it is reached.
    assert depth.depth_from_msl(0.0) == pytest.approx(-1.63)
    msl_in_nzvd2016 = depth.CD_NZVD2016_M + depth.MSL_M
    assert depth.depth_from_nzvd2016(msl_in_nzvd2016) == pytest.approx(depth.depth_from_msl(0.0))
    assert depth.depth_from_msl(-20.0) == pytest.approx(18.37)


def test_multibeam_heights_are_taken_as_already_on_chart_datum():
    assert depth.depth_from_multibeam(-30.0) == pytest.approx(30.0)
    assert depth.MULTIBEAM_DATUM_ABOVE_CD_M == 0.0


def test_sea_ends_at_mean_high_water_springs():
    assert depth.is_sea(0.0)
    assert depth.is_sea(-2.7)  # dries at low tide, but the spring tide covers it
    assert not depth.is_sea(-2.75)
    assert not depth.is_sea(-10.0)
    assert not depth.is_sea(np.nan)


# --- Merge order ----------------------------------------------------------------------


def test_merge_takes_the_most_trusted_source_that_has_a_value():
    lidar, multibeam, chart, background = blank(), blank(), blank(), blank()
    lidar[0, 0] = 5.0
    multibeam[0, 0:2] = 6.0
    chart[0, 0:3] = 7.0
    background[0, 0:4] = 8.0
    merged, source = depth.merge(
        [
            (depth.LIDAR, lidar),
            (depth.MULTIBEAM, multibeam),
            (depth.CHART_OLD, chart),
            (depth.BACKGROUND, background),
        ]
    )
    assert list(merged[0, 0:4]) == [5.0, 6.0, 7.0, 8.0]
    assert list(source[0, 0:4]) == [
        depth.LIDAR.code,
        depth.MULTIBEAM.code,
        depth.CHART_OLD.code,
        depth.BACKGROUND.code,
    ]
    assert np.isnan(merged[0, 4]) and source[0, 4] == 0


def test_the_declared_order_of_trust_is_lidar_multibeam_chart_background():
    keys = [src.key for src in depth.SOURCES]
    assert keys == [
        "lidar",
        "multibeam",
        "chart_recent",
        "chart_old",
        "chart_undated",
        "background",
    ]
    assert [src.code for src in depth.SOURCES] == [1, 2, 3, 4, 5, 6]  # 0 is "no depth"


def test_quality_follows_from_the_source():
    quality = {src.key: depth.QUALITY[src.quality]["key"] for src in depth.SOURCES}
    assert quality == {
        "lidar": "measured",
        "multibeam": "measured",
        "chart_recent": "charted",
        "chart_old": "old",
        "chart_undated": "old",
        "background": "background",
    }


def test_chart_cells_are_classed_by_the_year_their_survey_finished():
    years = np.array([[1962, 1989, 1990, 2010, 0]])
    assert list(depth.chart_source(years)[0]) == [
        depth.CHART_OLD.code,
        depth.CHART_OLD.code,
        depth.CHART_RECENT.code,
        depth.CHART_RECENT.code,
        depth.CHART_UNDATED.code,
    ]


# --- Fine raster to cells -----------------------------------------------------------------


def test_a_cell_needs_half_its_area_to_be_sea_with_data():
    fine = np.full(grid.fine_shape(10), np.nan)
    fine[0:10, 0:10] = 4.0  # cell (0, 0): all sea
    fine[0:10, 10:16] = 3.0  # cell (0, 1): 60% sea...
    fine[0:10, 16:20] = -8.0  # ...and 40% dune, which must not drag the depth
    fine[0:10, 20:24] = 3.0  # cell (0, 2): 40% sea, 60% land
    fine[0:10, 24:30] = -8.0
    fine[0:10, 30:34] = 3.0  # cell (0, 3): 40% sea, the rest unsurveyed water
    cells, land = depth.sea_cells(fine)
    assert cells[0, 0] == 4.0
    assert cells[0, 1] == 3.0 and land[0, 1] == pytest.approx(0.4)
    assert np.isnan(cells[0, 2]) and land[0, 2] == pytest.approx(0.6)
    assert np.isnan(cells[0, 3]) and land[0, 3] == 0


# --- Slope and roughness ------------------------------------------------------------------


def test_slope_of_a_plane_is_its_gradient():
    yy, xx = np.mgrid[0 : grid.NROWS * 10, 0 : grid.NCOLS * 10]
    fine = 5.0 + 0.1 * xx  # 1 m deeper every 100 m at 10 m cells
    slope = depth.slope_degrees(fine.astype(float), 10)
    assert slope[5, 5] == pytest.approx(np.degrees(np.arctan(0.01)))
    assert np.isnan(slope[0, 5]) and np.isnan(slope[5, 0])  # no neighbour beyond the edge


def test_slope_is_missing_beside_missing_data():
    fine = np.zeros(grid.fine_shape(10))
    fine[20, 20] = np.nan
    slope = depth.slope_degrees(fine, 10)
    assert np.isnan(slope[20, 19]) and np.isnan(slope[19, 20])
    assert np.isnan(slope[20, 20])
    assert slope[20, 18] == 0 and slope[18, 18] == 0


def test_slope_and_roughness_never_cross_the_seam_between_sources():
    # Two flat surfaces that disagree by 10 m where they meet: LiDAR west of fine
    # column 108, multibeam east of it. Merged first, the join would read as a cliff.
    rows, cols = grid.fine_shape(10)
    lidar = np.full((rows, cols), np.nan)
    other = np.full((rows, cols), np.nan)
    lidar[:, :108] = 5.0
    other[:, 108:] = 15.0
    merged_first = depth.slope_degrees(np.where(np.isnan(lidar), other, lidar), 10)
    assert np.nanmax(merged_first) > 20  # the mistake this guards against

    mine = np.zeros(grid.SHAPE, dtype=bool)
    mine[:, :11] = True  # the cells the merge took from the LiDAR, including the seam cell
    slope, rough = depth.cell_terrain(lidar, 10, mine)
    assert np.nanmax(slope) == 0 and np.nanmax(rough) == pytest.approx(0, abs=1e-9)
    assert slope[5, 10] == 0  # the seam cell: flat, from its own half only
    assert np.isnan(slope[5, 11]) and np.isnan(rough[5, 11])  # the other source's cells are empty


def test_roughness_is_zero_on_a_smooth_slope_and_the_scatter_on_broken_ground():
    yy, xx = np.mgrid[0 : grid.NROWS * 10, 0 : grid.NCOLS * 10]
    fine = (3.0 + 0.05 * xx + 0.02 * yy).astype(float)
    fine[10:20, 10:20] += np.where((xx[10:20, 10:20] + yy[10:20, 10:20]) % 2 == 0, 0.5, -0.5)
    fine[30:40, 0:10] = np.nan
    rough = depth.roughness(fine)
    assert rough[0, 0] == pytest.approx(0, abs=1e-6)  # a tilted plane is not rough
    assert rough[1, 1] == pytest.approx(0.5, abs=0.01)  # a half-metre checkerboard
    assert np.isnan(rough[3, 0])


# --- Chart surface --------------------------------------------------------------------------


def test_thin_averages_points_that_share_a_square():
    e, n, z = depth.thin([10.0, 20.0, 400.0], [10.0, 30.0, 400.0], [4.0, 6.0, 9.0], spacing_m=50)
    assert sorted(z) == [5.0, 9.0]
    assert sorted(e) == [15.0, 400.0]


def test_interpolate_reproduces_a_plane_and_is_empty_outside_the_points():
    corners_e = np.array([grid.WEST_E, grid.WEST_E + 5000, grid.WEST_E, grid.WEST_E + 5000.0])
    corners_n = np.array([grid.NORTH_N, grid.NORTH_N, grid.NORTH_N - 5000, grid.NORTH_N - 5000.0])
    value = 10 + (corners_e - grid.WEST_E) / 1000
    surface = depth.interpolate(corners_e, corners_n, value)
    easting, _ = grid.cell_centre(20, 30)
    assert surface[20, 30] == pytest.approx(10 + (easting - grid.WEST_E) / 1000)
    assert np.isnan(surface[20, 60])  # beyond the points: no extrapolation
    assert np.isnan(depth.interpolate(corners_e[:2], corners_n[:2], value[:2])).all()


def test_interpolated_depth_is_kept_inside_the_charted_depth_band():
    surface = np.array([[3.0, 7.0, 12.0, 8.0]])
    shallowest = np.array([[5.0, 5.0, 5.0, np.nan]])
    deepest = np.array([[10.0, 10.0, 10.0, np.nan]])
    assert list(depth.clamp_to_depth_areas(surface, shallowest, deepest)[0]) == [
        5.0,
        7.0,
        10.0,
        8.0,
    ]


def test_a_sounding_sets_the_depth_of_its_own_cell():
    surface = np.full(grid.SHAPE, 15.0)
    easting, northing = grid.cell_centre(np.array([3, 3, 7]), np.array([4, 4, 9]))
    soundings = np.column_stack([easting + [10, -20, 0], northing, [8.0, 9.0, 21.5]])
    outside = np.array([[grid.WEST_E - 500.0, grid.NORTH_N - 50.0, 2.0]])
    result = depth.honour_soundings(surface, np.vstack([soundings, outside]))
    assert result[3, 4] == 8.5  # two soundings in one cell: their mean
    assert result[7, 9] == 21.5
    assert result[3, 5] == 15.0 and (result != 15.0).sum() == 2
