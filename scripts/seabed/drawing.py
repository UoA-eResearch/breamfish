"""The drawing grids: depth and bottom type on a 20 m grid, for the map to paint when
zoomed in.

The 100 m grid is the one every computed number on the site comes from. It is too
coarse to look at closely: a cell is a hectare, the LiDAR and the multibeam saw far
more than that, and the chart and the habitat map are drawn as lines, not as squares.
This module lays the same sources out, in the same order of trust, on a grid five
times finer:

- depth is the LiDAR or the multibeam where a 20 m square has one of its own, and
  elsewhere the surface through the charted soundings and contours, read at 20 m;
- bottom type follows the outlines of charted rock and of the habitat map as they are
  drawn, where the 100 m grid can only say which hectare they pass through.

It adds no information to the charted water, where there is none to add, and it never
feeds the 100 m grid or anything computed from it.
"""

from __future__ import annotations

import numpy as np

from seabed import bottom, depth, grid, publish

CELL_M = 20
SHAPE = grid.fine_shape(CELL_M)
FACTOR = grid.fine_factor(CELL_M)

# Light smoothing of the finished surface, in 20 m cells. Survey noise on flat sand is a
# few centimetres; unsmoothed, every depth band would end in a speckled fringe.
SMOOTH_CELLS = 1.0

# Water with no survey of its own takes the nearest surveyed depth out to REACH_CELLS
# from a survey, and the charted surface from FADE_CELLS on, sliding from one to the other.
REACH_CELLS = 2.0
FADE_CELLS = 6.0

# The surface is carried this many cells past the shore, onto the land, repeating the
# nearest water. The map draws its own land over the top, so its coastline is the one
# seen, with no gap or overlap where it and the chart's differ by a few tens of metres.
# Those cells are marked in the source grid with PAST_SHORE added to the source code,
# and nothing but the painting uses them.
BLEED_CELLS = 5.0
PAST_SHORE = 128


def centres():
    """Two arrays of SHAPE: the easting and northing of every 20 m cell centre."""
    rows, cols = np.mgrid[0 : SHAPE[0], 0 : SHAPE[1]]
    return grid.WEST_E + (cols + 0.5) * CELL_M, grid.NORTH_N - (rows + 0.5) * CELL_M


def halve(fine: np.ndarray, min_valid: int = 2) -> np.ndarray:
    """A 10 m raster as 20 m cells: the mean of each cell's valid values.

    NaN where fewer than min_valid of the four have a value.
    """
    rows, cols = fine.shape
    blocks = fine.reshape(rows // 2, 2, cols // 2, 2)
    valid = ~np.isnan(blocks)
    count = valid.sum(axis=(1, 3))
    total = np.where(valid, blocks, 0.0).sum(axis=(1, 3))
    return np.where(count >= min_valid, total / np.maximum(count, 1), np.nan)


def spread(coarse: np.ndarray) -> np.ndarray:
    """A 100 m grid repeated onto the 20 m grid, each cell as a block of 25."""
    return np.repeat(np.repeat(coarse, FACTOR, axis=0), FACTOR, axis=1)


def dots(coarse: np.ndarray) -> np.ndarray:
    """A 100 m grid of marks on the 20 m grid, each marked cell as a dot and not a square.

    The dot is the cell with its four corners left off. A note made at one point is not
    a square of seabed, and drawn as one it reads as a fault in the map.
    """
    dot = np.ones((FACTOR, FACTOR), dtype=bool)
    dot[[0, 0, -1, -1], [0, -1, 0, -1]] = False
    return np.where(np.tile(dot, coarse.shape), spread(coarse), 0).astype(coarse.dtype)


def between_centres(coarse: np.ndarray) -> np.ndarray:
    """A 100 m grid drawn smoothly on the 20 m grid: a cubic spline through the cell centres.

    Gaps (NaN) are first filled from the nearest cell with a value, so the spline has
    something to run through at the shore; the caller masks the land back out.
    """
    from scipy.ndimage import distance_transform_edt, zoom

    gaps = np.isnan(coarse)
    if gaps.all():
        return np.full(SHAPE, np.nan)
    nearest = distance_transform_edt(gaps, return_distances=False, return_indices=True)
    filled = coarse[tuple(nearest)]
    return zoom(filled, FACTOR, order=3, mode="nearest", grid_mode=True)


def surface(
    lidar_fine: np.ndarray,
    multibeam_fine: np.ndarray,
    charted_depth: np.ndarray,
    cell_source: np.ndarray,
    charted_land: np.ndarray,
    charted: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Depth and its source on the 20 m grid.

    lidar_fine is LiDAR depth on the 10 m grid, already cut off at the depth LiDAR is
    trusted to; multibeam_fine is the multibeam on the 20 m grid; charted_depth is the
    depth of the water no survey reached, on the 20 m grid (the surface through the
    chart's soundings and contours); all in metres below chart datum with NaN for no
    data. cell_source is the merged 100 m grid's source. charted_land and charted are
    boolean 20 m grids: where the chart draws land, and where it says anything at all.

    Returns (depth, source code). Land and water nothing is known about are NaN and 0,
    except for a fringe of BLEED_CELLS past the shore, which repeats the nearest water
    and carries its source code plus PAST_SHORE.

    The shoreline is the edge of the survey where a survey reaches the shore, and the
    chart's own coastline elsewhere, so it is drawn at 20 m and not in 100 m steps.
    """
    from scipy.ndimage import distance_transform_edt

    lidar_sea = halve(np.where(depth.is_sea(lidar_fine), lidar_fine, np.nan))
    lidar_land = ~np.isnan(lidar_fine) & ~depth.is_sea(lidar_fine)
    lidar_land = halve(lidar_land.astype(np.float64)) >= 0.5
    multibeam = np.where(depth.is_sea(multibeam_fine), multibeam_fine, np.nan)

    out = np.full(SHAPE, np.nan)
    source = np.zeros(SHAPE, dtype=np.uint8)
    for src, values in ((depth.LIDAR, lidar_sea), (depth.MULTIBEAM, multibeam)):
        take = np.isnan(out) & ~np.isnan(values) & ~lidar_land
        out[take] = values[take]
        source[take] = src.code

    # The rest of the water: not land on the chart, or, where there is no chart, a
    # 100 m cell that has a depth. It takes the charted surface.
    water = np.where(charted, ~charted_land, spread(cell_source) != 0) & ~lidar_land
    rest = np.isnan(out) & water
    fill = charted_depth
    surveyed = ~np.isnan(out)
    if surveyed.any():
        # Hard against a survey (a gap in it, or the strip between it and the charted
        # shore) the survey's own nearest depth is the better guess; it gives way to
        # the charted surface over the next few cells.
        distance, nearest = distance_transform_edt(~surveyed, return_indices=True)
        share = np.clip((FADE_CELLS - distance) / (FADE_CELLS - REACH_CELLS), 0.0, 1.0)
        near = out[tuple(nearest)]
        fill = np.where(np.isnan(fill), near, share * near + (1 - share) * fill)
    out[rest] = fill[rest]

    # Each such cell is credited to the source of its 100 m cell, or of the nearest
    # one that has a source where the chart's shoreline runs inside a cell of land.
    if (cell_source != 0).any():
        nearest_cell = distance_transform_edt(
            cell_source == 0, return_distances=False, return_indices=True
        )
        source[rest] = spread(cell_source[tuple(nearest_cell)])[rest]
    source[np.isnan(out)] = 0
    out[source == 0] = np.nan

    # A fringe past the shore, for the map's own land to cover.
    if (source != 0).any():
        distance, nearest = distance_transform_edt(source == 0, return_indices=True)
        fringe = (source == 0) & (distance <= BLEED_CELLS)
        out[fringe] = out[tuple(nearest)][fringe]
        source[fringe] = source[tuple(nearest)][fringe] + PAST_SHORE
    return publish.smooth(out, SMOOTH_CELLS), source


def bottom_type(
    rock_areas: np.ndarray,
    rock_marks: np.ndarray,
    samples: np.ndarray,
    habitat: np.ndarray,
    source: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Bottom class and which source said so, on the 20 m grid.

    The same sources in the same order as the 100 m grid. The two that are drawn as
    areas, charted rock (rock_areas) and the habitat map (habitat), come in at 20 m and
    keep their outlines. The two that are notes at a point, a charted rock (rock_marks)
    and a seabed sample (samples), come in on the 100 m grid and are drawn as a dot on
    the cell they speak for. source is the drawing grid's depth source: only water is
    classed, and the fringe past the shore repeats the nearest water.
    """
    from scipy.ndimage import distance_transform_edt

    kind, kind_source = bottom.merge(
        [
            (bottom.CHART_ROCK, rock_areas),
            (bottom.CHART_ROCK, dots(rock_marks)),
            (bottom.CHART_SAMPLE, dots(samples)),
            (bottom.HABITAT_MAP, habitat),
        ]
    )
    water = (source != 0) & (source < PAST_SHORE)
    kind[~water] = bottom.UNKNOWN
    kind_source[~water] = bottom.NO_SOURCE
    if water.any():
        nearest = distance_transform_edt(~water, return_distances=False, return_indices=True)
        fringe = source >= PAST_SHORE
        kind[fringe] = kind[tuple(nearest)][fringe]
        kind_source[fringe] = kind_source[tuple(nearest)][fringe]
    return kind, kind_source
