"""The project grid: where it sits, and how fine rasters fold into its cells."""

import numpy as np
import pytest
from rasterio.warp import transform

from seabed import grid


def test_the_grid_contains_the_whole_study_box():
    # Walk the edge of the latitude/longitude box and project it with PROJ.
    lons = np.linspace(grid.BOX_WEST, grid.BOX_EAST, 50)
    lats = np.linspace(grid.BOX_SOUTH, grid.BOX_NORTH, 50)
    edge_lon = np.concatenate([lons, lons, np.full(50, grid.BOX_WEST), np.full(50, grid.BOX_EAST)])
    edge_lat = np.concatenate(
        [np.full(50, grid.BOX_SOUTH), np.full(50, grid.BOX_NORTH), lats, lats]
    )
    easting, northing = transform("EPSG:4326", grid.CRS, list(edge_lon), list(edge_lat))
    rows, cols = grid.cell_of(np.array(easting), np.array(northing))
    assert grid.inside(rows, cols).all()
    # And it is tight: the box reaches the outermost row and column on every side.
    assert rows.min() == 0 and rows.max() == grid.NROWS - 1
    assert cols.min() == 0 and cols.max() == grid.NCOLS - 1


def test_cells_are_whole_hundreds_of_metres_counted_from_the_north_west():
    assert grid.WEST_E % grid.CELL_M == 0 and grid.NORTH_N % grid.CELL_M == 0
    assert grid.cell_of(grid.WEST_E, grid.NORTH_N - 0.01) == (0, 0)
    assert grid.cell_of(grid.WEST_E + 100, grid.NORTH_N - 100.01) == (1, 1)
    # The south-east corner cell, and one step beyond it.
    assert grid.cell_of(grid.EAST_E - 0.01, grid.SOUTH_N + 0.01) == (grid.NROWS - 1, grid.NCOLS - 1)
    assert not grid.inside(*grid.cell_of(grid.EAST_E, grid.SOUTH_N + 50))
    assert not grid.inside(*grid.cell_of(grid.WEST_E - 0.01, grid.NORTH_N - 50))


def test_a_cell_centre_falls_back_in_its_own_cell():
    for row, col in [(0, 0), (17, 250), (grid.NROWS - 1, grid.NCOLS - 1)]:
        easting, northing = grid.cell_centre(row, col)
        assert grid.cell_of(easting, northing) == (row, col)
    assert grid.cell_centre(0, 0) == (grid.WEST_E + 50, grid.NORTH_N - 50)


def test_fine_grids_must_nest():
    assert grid.fine_shape(10) == (grid.NROWS * 10, grid.NCOLS * 10)
    assert grid.fine_shape(20) == (grid.NROWS * 5, grid.NCOLS * 5)
    with pytest.raises(ValueError):
        grid.fine_factor(30)


def test_block_mean_averages_each_cell_and_ignores_missing_values():
    fine = np.zeros(grid.fine_shape(20))
    fine[0:5, 0:5] = 4.0  # all of cell (0, 0)
    fine[0:5, 5:10] = np.arange(25).reshape(5, 5)  # cell (0, 1): mean 12
    fine[5:10, 0:5] = 10.0
    fine[5:8, 0:5] = np.nan  # cell (1, 0): 15 of 25 missing, the rest 10
    cells = grid.block_mean(fine)
    assert cells.shape == grid.SHAPE
    assert cells[0, 0] == 4.0
    assert cells[0, 1] == 12.0
    assert np.isnan(cells[1, 0])  # under half the cell has data
    assert grid.block_mean(fine, min_fraction=0.3)[1, 0] == 10.0
    assert cells[2, 2] == 0.0


def test_block_fraction_is_the_share_of_the_cell():
    mask = np.zeros(grid.fine_shape(10), dtype=bool)
    mask[0:10, 0:3] = True
    assert grid.block_fraction(mask)[0, 0] == pytest.approx(0.3)
    assert grid.block_fraction(mask)[0, 1] == 0
