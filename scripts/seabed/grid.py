"""The project grid: NZTM (EPSG:2193), 100 m cells, rows counted from the north.

Every seabed layer is one array of NROWS by NCOLS on this grid. Finer source rasters
(10 m LiDAR, 20 m multibeam) are first laid out on a grid that nests exactly inside it,
so a cell is always a whole block of fine cells and nothing is resampled twice.
"""

from __future__ import annotations

import numpy as np

CRS = "EPSG:2193"
CELL_M = 100

# The study box in latitude and longitude (docs/data-sources.md).
BOX_WEST, BOX_SOUTH, BOX_EAST, BOX_NORTH = 174.38, -36.12, 174.80, -35.78

# The smallest rectangle of whole 100 m NZTM cells that contains the study box. In NZTM
# the box is slightly rotated (grid north is about 0.9 degrees off true north here), so
# the grid's corners reach a little beyond it. tests/test_seabed_grid.py checks the fit.
WEST_E = 1_724_100
NORTH_N = 6_039_600
NCOLS = 386
NROWS = 384
EAST_E = WEST_E + NCOLS * CELL_M
SOUTH_N = NORTH_N - NROWS * CELL_M
SHAPE = (NROWS, NCOLS)


def cell_of(easting, northing):
    """(row, col) of the cell containing a point. Works on numbers or arrays.

    A point outside the grid gives an index outside 0..NROWS-1 or 0..NCOLS-1; callers
    that take points from outside sources must check with `inside`.
    """
    col = np.floor((np.asarray(easting) - WEST_E) / CELL_M).astype(int)
    row = np.floor((NORTH_N - np.asarray(northing)) / CELL_M).astype(int)
    return row, col


def inside(row, col):
    row, col = np.asarray(row), np.asarray(col)
    return (row >= 0) & (row < NROWS) & (col >= 0) & (col < NCOLS)


def cell_centre(row, col):
    """(easting, northing) of a cell's centre."""
    easting = WEST_E + (np.asarray(col) + 0.5) * CELL_M
    northing = NORTH_N - (np.asarray(row) + 0.5) * CELL_M
    return easting, northing


def centres():
    """Two NROWS by NCOLS arrays: the easting and northing of every cell centre."""
    rows, cols = np.mgrid[0:NROWS, 0:NCOLS]
    return cell_centre(rows, cols)


def fine_shape(res_m: int) -> tuple[int, int]:
    """Shape of the nested fine grid with cells of res_m metres."""
    factor = fine_factor(res_m)
    return NROWS * factor, NCOLS * factor


def fine_factor(res_m: int) -> int:
    if CELL_M % res_m:
        raise ValueError(f"{res_m} m cells do not nest inside {CELL_M} m cells")
    return CELL_M // res_m


def blocks(fine: np.ndarray) -> np.ndarray:
    """View a nested fine grid as (NROWS, NCOLS, n): the n fine cells of each cell."""
    factor = fine.shape[0] // NROWS
    if fine.shape != (NROWS * factor, NCOLS * factor):
        raise ValueError(f"array of shape {fine.shape} does not nest inside the grid")
    return (
        fine.reshape(NROWS, factor, NCOLS, factor)
        .transpose(0, 2, 1, 3)
        .reshape(NROWS, NCOLS, factor * factor)
    )


def block_mean(fine: np.ndarray, min_fraction: float = 0.5) -> np.ndarray:
    """Mean of the valid (not NaN) fine cells in each cell.

    A cell with less than min_fraction of its area valid is NaN: a cell is not
    described by a corner of it.
    """
    cells = blocks(fine)
    valid = ~np.isnan(cells)
    count = valid.sum(axis=2)
    total = np.where(valid, cells, 0.0).sum(axis=2)
    enough = count >= min_fraction * cells.shape[2]
    return np.where(enough, total / np.maximum(count, 1), np.nan)


def block_fraction(mask: np.ndarray) -> np.ndarray:
    """Share of each cell's fine cells where the boolean mask is true."""
    return blocks(mask.astype(np.float32)).mean(axis=2)
