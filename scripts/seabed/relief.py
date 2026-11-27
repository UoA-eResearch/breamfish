"""Shaded relief, and how rough the ground is at the scale of a few metres.

Both are worked out on one survey's own grid: the LiDAR at 2 m, the multibeam at 20 m.
A slope is never taken across the join between two surveys, and nothing is shaded where
the depth is only charted: between soundings the surface is a guess, and shading a guess
would draw reefs that nobody measured.

The shading is flat: light and shadow laid over the map, not a tilted view. It is
published as map tiles in Web Mercator (scripts/seabed/tiles.py). Each pixel is black
with some transparency (a face turned away from the light) or white with some
transparency (a face turned towards it), so the same tiles sit over any layer in the
light theme and the dark one.

Everything about how it is drawn is a judgement made here by looking at the result, not
a published method: the lights, the exaggeration, the smoothing and the tone curve.
"""

from __future__ import annotations

import numpy as np

from seabed import depth, grid

# --- The lights -------------------------------------------------------------------------
#
# Three lights, all from the north-west half of the sky: the mapping convention that
# keeps a hill from reading as a hollow. On gentle ground they add up to one light from
# the north-west, a little higher in the sky than any of them. They differ on steep
# ground, where a face turned right away from the main light still catches one of the
# other two, so the shadow side of a reef keeps some shape.
# (azimuth in degrees clockwise from grid north, weight)
LIGHTS = ((315.0, 0.5), (255.0, 0.25), (15.0, 0.25))
ALTITUDE_DEG = 45.0

# Heights are multiplied by this before shading. The bay is very flat: the open seabed
# slopes at well under a degree and most reef edges at a few degrees, which a light at
# 45 degrees barely tells from level ground.
EXAGGERATION = 8.0

# A Gaussian of this many metres is run over each survey's depths before the slope is
# taken. A sounding is good to a few centimetres at best, and over cells of 2 m that is
# a slope of a degree or more: unsmoothed, flat sand comes out speckled.
SMOOTH_M = {2: 3.0, 20: 20.0}

# Shade weaker than this is left out altogether, and the rest is stretched over what is
# left. On flat sand the LiDAR's noise, smoothed as above, still shades to about this
# strength, so below it there is nothing to show; and a tile of flat seabed comes out
# empty, which is most of what keeps the archives small (16 MB; 22 MB at 0.06).
FLOOR = 0.10

NO_SHADE = -128  # in a stored shade grid: nothing measured here


def halo_cells(res_m: int) -> int:
    """How far past a block's edge to read so that its shade is the same as the whole
    grid's would be: the reach of the smoothing, and one cell for the slope."""
    return int(np.ceil(4 * SMOOTH_M[res_m] / res_m)) + 1


def smooth(values: np.ndarray, sigma_cells: float) -> np.ndarray:
    """Gaussian smoothing that skips NaN and leaves NaN where it was."""
    from scipy.ndimage import gaussian_filter

    valid = ~np.isnan(values)
    kwargs = {"sigma": sigma_cells, "mode": "constant", "truncate": 4.0}
    total = gaussian_filter(np.where(valid, values, 0.0).astype(np.float32), **kwargs)
    weight = gaussian_filter(valid.astype(np.float32), **kwargs)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(valid, total / weight, np.nan)


def shade(fine_depth: np.ndarray, res_m: int) -> np.ndarray:
    """Signed shade of a depth raster (metres, positive down, NaN = nothing to shade).

    0 is level ground, +1 a face square to the light, -1 a face in full shadow. NaN where
    the cell or one of its four neighbours has no depth, and on the outer edge: a slope
    needs both sides.
    """
    height = -smooth(fine_depth, SMOOTH_M[res_m] / res_m) * EXAGGERATION
    east = np.full(height.shape, np.nan, dtype=np.float32)
    north = np.full(height.shape, np.nan, dtype=np.float32)
    east[1:-1, 1:-1] = (height[1:-1, 2:] - height[1:-1, :-2]) / (2 * res_m)
    north[1:-1, 1:-1] = (height[:-2, 1:-1] - height[2:, 1:-1]) / (2 * res_m)  # rows run south

    # The unit normal of the surface is (-east, -north, 1) / length.
    length = np.sqrt(1 + east**2 + north**2)
    altitude = np.radians(ALTITUDE_DEG)
    lit = np.zeros(height.shape, dtype=np.float32)
    for azimuth, weight in LIGHTS:
        a = np.radians(azimuth)
        towards = (
            -east * np.sin(a) * np.cos(altitude)
            - north * np.cos(a) * np.cos(altitude)
            + np.sin(altitude)
        ) / length
        # A face turned away from a light gets nothing from it, not less than nothing.
        lit += weight * np.maximum(towards, 0.0)
    # Level ground is lit by sin(altitude); a face square to the light by 1. The same
    # change in light counts the same either side of level, so a low sand ridge has a
    # shadow as strong as its highlight. Deep shadow is eased towards -1 and not cut off
    # at it, or every steep face of a reef would be the same black.
    level = np.sin(altitude)
    change = (lit - level) / (1 - level)
    shaded = np.where(change >= 0, np.minimum(change, 1.0), np.tanh(change))
    return np.where(np.isnan(fine_depth), np.nan, shaded)


def to_stored(shaded: np.ndarray) -> np.ndarray:
    """Signed shade as int8, -127 to 127, with NO_SHADE where it is NaN."""
    stored = np.rint(np.clip(shaded, -1, 1) * 127)
    return np.where(np.isnan(shaded), NO_SHADE, stored).astype(np.int8)


# A tile is a picture with a palette: entry 0 is clear, 1 to STEPS are black and
# STEPS + 1 to 2 * STEPS are white, each from nearly clear to solid. Steps this small
# cannot be seen in a texture, and so few distinct values make a small file.
STEPS = 31
PALETTE = {
    0: (0, 0, 0, 0),
    **{i: (0, 0, 0, round(255 * i / STEPS)) for i in range(1, STEPS + 1)},
    **{STEPS + i: (255, 255, 255, round(255 * i / STEPS)) for i in range(1, STEPS + 1)},
}


def pixels(stored: np.ndarray) -> np.ndarray:
    """Stored shade as palette entries: how strong the shade is above FLOOR, and whether
    it is shadow or light."""
    strength = np.abs(stored.astype(np.float32)) / 127
    step = np.rint(np.clip((strength - FLOOR) / (1 - FLOOR), 0, 1) * STEPS).astype(np.uint8)
    step[stored == NO_SHADE] = 0
    return np.where((stored > 0) & (step > 0), step + STEPS, step).astype(np.uint8)


# --- Which water each survey shades --------------------------------------------------------


def lidar_sea(height: np.ndarray, max_depth_m: float) -> np.ndarray:
    """LiDAR heights (NZVD2016) as the depths that are shaded: sea, and no deeper than
    the LiDAR is trusted to. Everything else is NaN."""
    fine = depth.depth_from_nzvd2016(height)
    with np.errstate(invalid="ignore"):
        return np.where(depth.is_sea(fine) & (fine <= max_depth_m), fine, np.nan)


def cover(valid: np.ndarray, factor: int) -> np.ndarray:
    """Share of each block of factor by factor fine cells that is true."""
    rows, cols = valid.shape
    blocks = valid.reshape(rows // factor, factor, cols // factor, factor)
    return blocks.mean(axis=(1, 3), dtype=np.float32)


# --- Rough ground ---------------------------------------------------------------------------
#
# The roughness layer of the 100 m grid (depth.roughness) is the spread of depth about
# one plane through a whole hectare, from 10 m cells. This one looks at the scale of a
# reef patch: the spread about a plane through each 10 m square of 2 m LiDAR, and then
# what the rough part of the hectare scores.

WINDOW_M = 10
# A hectare's score is its third roughest 10 m square. A patch of reef is often far
# smaller than a hectare, and a mean or a median loses it in the sand around it. Not the
# roughest square alone, so that one stray return (a moored boat, a school of fish) does
# not mark a hectare. docs/seabed-report.md has how the other choices compare; this one
# was made after reading that table.
CELL_RANK = 3


def window_roughness(fine_depth: np.ndarray, res_m: int, min_fraction: float = 0.6) -> np.ndarray:
    """RMS of depth about the best-fit plane of each WINDOW_M square, in metres.

    fine_depth is whole windows of cells of res_m. NaN where less than min_fraction of
    a window has a depth.
    """
    factor = WINDOW_M // res_m
    rows, cols = fine_depth.shape
    cells = (
        fine_depth.reshape(rows // factor, factor, cols // factor, factor)
        .transpose(0, 2, 1, 3)
        .reshape(rows // factor, cols // factor, factor * factor)
    )
    yy, xx = np.mgrid[0:factor, 0:factor]
    x = (xx - (factor - 1) / 2).ravel()
    y = (yy - (factor - 1) / 2).ravel()
    design = np.stack([np.ones_like(x), x, y])  # (3, n)

    valid = ~np.isnan(cells)
    usable = valid.sum(axis=2) >= max(4, min_fraction * factor * factor)
    out = np.full(usable.shape, np.nan, dtype=np.float64)
    if not usable.any():
        return out
    v = valid[usable].astype(np.float64)
    z = np.where(valid[usable], cells[usable], 0.0).astype(np.float64)
    lhs = np.einsum("in,jn,cn->cij", design, design, v)
    rhs = np.einsum("in,cn->ci", design, z)
    solvable = np.abs(np.linalg.det(lhs)) > 1e-6
    coeffs = np.linalg.solve(lhs[solvable], rhs[solvable][..., None])[..., 0]
    residual = (z[solvable] - coeffs @ design) * v[solvable]
    rms = np.sqrt((residual**2).sum(axis=1) / v[solvable].sum(axis=1))
    where = np.nonzero(usable)
    out[where[0][solvable], where[1][solvable]] = rms
    return out


def cell_windows(windows: np.ndarray, min_fraction: float = 0.5):
    """Window roughness as (NROWS, NCOLS, n): the n windows of each 100 m cell, and the
    boolean grid of cells where at least min_fraction of them have a value."""
    factor = grid.CELL_M // WINDOW_M
    rows, cols = windows.shape
    cells = (
        windows.reshape(rows // factor, factor, cols // factor, factor)
        .transpose(0, 2, 1, 3)
        .reshape(rows // factor, cols // factor, factor * factor)
    )
    return cells, (~np.isnan(cells)).sum(axis=2) >= min_fraction * factor * factor


def cell_roughness(windows: np.ndarray, rank: int = CELL_RANK) -> np.ndarray:
    """Window roughness summarised to 100 m cells: each cell's rank-th roughest window.
    NaN where less than half of a cell's windows have a value."""
    cells, enough = cell_windows(windows)
    ordered = np.sort(np.where(np.isnan(cells), -np.inf, cells), axis=2)
    return np.where(enough, ordered[:, :, -rank], np.nan)
