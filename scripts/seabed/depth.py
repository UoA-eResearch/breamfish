"""Depth: vertical datums, the order of trust between sources, and the merge.

Everything is published as depth in metres below chart datum at Marsden Point, positive
down. That is the zero of the LINZ charts of this bay and of the tide predictions the
site already shows, so depth plus tide height is the water over a spot. A negative
depth is ground that dries at low tide.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from seabed import grid

# --- Vertical datums ------------------------------------------------------------------
#
# Chart datum (CD) at Marsden Point is defined by a benchmark, and that benchmark has a
# surveyed height in NZVD2016, the datum of the LiDAR. The two published figures give
# the offset directly, with no tidal assumption in between:
#
#   LINZ, "Standard port datum descriptions": Marsden Point chart datum is 4.816 m
#   below the RNZN benchmark (geodetic code DJM9).
#   LINZ Geodetic Database, mark DJM9: NZVD2016 height 3.07 m (order 3V, authorised
#   30 November 2018).
#
# Both were read on 26 November 2026. See docs/data-sources.md.
CD_BELOW_BENCHMARK_M = 4.816
BENCHMARK_NZVD2016_M = 3.07
CD_NZVD2016_M = BENCHMARK_NZVD2016_M - CD_BELOW_BENCHMARK_M  # -1.746: CD is below NZVD2016

# LINZ, "Standard port tidal levels", Marsden Point, metres above chart datum, from the
# predictions for 1 July 2026 to 30 June 2027.
MHWS_M = 2.75  # mean high water springs: the line between sea and land used here
MSL_M = 1.63  # mean sea level: the zero of the global background grid
LAT_M = 0.18  # lowest astronomical tide

# The LINZ multibeam model states its datum as "Approximate Lowest Astronomical Tide".
# LINZ describes chart datum itself as a level that "usually approximates" LAT, and its
# hydrographic surveys are reduced to chart datum, so the model is taken to be on chart
# datum as it stands. If it were on true LAT instead, its depths here would be 0.18 m
# too large. That is a tenth of the model's stated vertical accuracy (1.7 m at 95%).
MULTIBEAM_DATUM_ABOVE_CD_M = 0.0


def depth_from_nzvd2016(height):
    """Depth below chart datum of a height in NZVD2016 (LiDAR)."""
    return CD_NZVD2016_M - np.asarray(height, dtype=np.float64)


def depth_from_msl(height):
    """Depth below chart datum of a height above mean sea level (global grid)."""
    return -(np.asarray(height, dtype=np.float64) + MSL_M)


def depth_from_multibeam(height):
    """Depth below chart datum of a multibeam model value (a negative height)."""
    return -(np.asarray(height, dtype=np.float64) + MULTIBEAM_DATUM_ABOVE_CD_M)


def is_sea(depth):
    """True where a depth is below mean high water springs. NaN is not sea."""
    with np.errstate(invalid="ignore"):
        return np.asarray(depth) > -MHWS_M


# --- Sources, in order of trust ---------------------------------------------------------


@dataclass(frozen=True)
class Source:
    code: int  # the byte stored in the depth_source grid; 0 means land or no data
    key: str
    label: str
    quality: int  # index into QUALITY


# What the site can honestly say about a depth, from which source it came.
QUALITY = (
    {"key": "none", "label": "No depth"},
    {"key": "measured", "label": "Measured", "detail": "A modern survey covers this spot."},
    {
        "key": "charted",
        "label": "Charted",
        "detail": "Estimated between charted soundings and contours from a survey since 1990.",
    },
    {
        "key": "old",
        "label": "Old survey",
        "detail": "Estimated between sparse charted soundings from a survey before 1990 "
        "or of unknown date.",
    },
    {
        "key": "background",
        "label": "Rough guide",
        "detail": "No survey or chart detail here; a coarse global grid only.",
    },
)

LIDAR = Source(1, "lidar", "Airborne LiDAR, March 2025", 1)
MULTIBEAM = Source(2, "multibeam", "Multibeam sonar, 1999 to 2004", 1)
CHART_RECENT = Source(3, "chart_recent", "Chart soundings, surveyed since 1990", 2)
CHART_OLD = Source(4, "chart_old", "Chart soundings, surveyed before 1990", 3)
CHART_UNDATED = Source(5, "chart_undated", "Chart soundings, survey date not recorded", 3)
BACKGROUND = Source(6, "background", "Global grid (GEBCO)", 4)

# The merge takes the first source in this order that has a value for a cell. The three
# chart classes are one surface (see chart_source); they never compete with each other.
SOURCES = (LIDAR, MULTIBEAM, CHART_RECENT, CHART_OLD, CHART_UNDATED, BACKGROUND)

# A chart survey finished in or after this year counts as recent. The chart's "quality of
# data" areas date the bay's surveys to 1955 to 1962, 1981 to 1982, and 1999 onwards; the
# chart itself rates the first group as its lowest assessed category and the last as its
# best, so the line sits between the echo-sounder surveys of the 1980s and the modern ones.
RECENT_SURVEY_YEAR = 1990


def merge(layers) -> tuple[np.ndarray, np.ndarray]:
    """Combine depth grids in order of trust.

    layers is a list of (Source, depth array) with NaN where a source has nothing, most
    trusted first. Returns the merged depth and the code of the source each cell came
    from (0 where no source has a value).
    """
    depth = np.full(grid.SHAPE, np.nan, dtype=np.float64)
    source = np.zeros(grid.SHAPE, dtype=np.uint8)
    for src, values in layers:
        take = np.isnan(depth) & ~np.isnan(values)
        depth[take] = values[take]
        source[take] = src.code
    return depth, source


def chart_source(survey_year: np.ndarray) -> np.ndarray:
    """The chart source code for each cell, from the year its survey finished (0 = unknown)."""
    return np.where(
        survey_year == 0,
        CHART_UNDATED.code,
        np.where(survey_year >= RECENT_SURVEY_YEAR, CHART_RECENT.code, CHART_OLD.code),
    ).astype(np.uint8)


# --- From a fine raster to cells --------------------------------------------------------


def sea_cells(fine_depth: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Summarise a fine depth raster (NaN = no data) to the 100 m grid.

    Returns (depth, land_fraction). A cell's depth is the mean of its fine cells that are
    sea, and it has one only when at least half the cell is sea with data. land_fraction
    is the share of the cell at or above mean high water springs.
    """
    sea = is_sea(fine_depth)
    depth = grid.block_mean(np.where(sea, fine_depth, np.nan), min_fraction=0.5)
    land = ~np.isnan(fine_depth) & ~sea
    return depth, grid.block_fraction(land)


# --- Slope and roughness ----------------------------------------------------------------
#
# Both are computed on one source's own fine raster and only then summarised, so a
# gradient is never taken across the join between two sources.


def slope_degrees(fine_depth: np.ndarray, res_m: float) -> np.ndarray:
    """Steepest slope at each fine cell, in degrees, by central differences.

    NaN where the cell or one of its four neighbours is missing, and on the outer edge.
    """
    out = np.full(fine_depth.shape, np.nan, dtype=np.float64)
    dz_dx = (fine_depth[1:-1, 2:] - fine_depth[1:-1, :-2]) / (2 * res_m)
    dz_dy = (fine_depth[2:, 1:-1] - fine_depth[:-2, 1:-1]) / (2 * res_m)
    out[1:-1, 1:-1] = np.degrees(np.arctan(np.hypot(dz_dx, dz_dy)))
    out[np.isnan(fine_depth)] = np.nan
    return out


def roughness(fine_depth: np.ndarray, min_fraction: float = 0.5) -> np.ndarray:
    """How uneven the bottom is within each cell, in metres.

    The standard deviation of depth about the cell's best-fit plane, so a smooth slope
    scores zero and broken ground scores high. NaN where less than min_fraction of the
    cell has data.
    """
    cells = grid.blocks(fine_depth)
    n_fine = cells.shape[2]
    factor = int(round(n_fine**0.5))
    yy, xx = np.mgrid[0:factor, 0:factor]
    x = (xx - (factor - 1) / 2).ravel()
    y = (yy - (factor - 1) / 2).ravel()

    valid = ~np.isnan(cells)
    z = np.where(valid, cells, 0.0)
    count = valid.sum(axis=2)
    usable = count >= max(4, min_fraction * n_fine)

    v = valid[usable].astype(np.float64)
    zu = z[usable]
    # Normal equations of z = a + b x + c y over the valid fine cells of each cell.
    design = np.stack([np.ones_like(x), x, y])  # (3, n)
    lhs = np.einsum("in,jn,cn->cij", design, design, v)
    rhs = np.einsum("in,cn->ci", design, zu)
    solvable = np.abs(np.linalg.det(lhs)) > 1e-6
    coeffs = np.linalg.solve(lhs[solvable], rhs[solvable][..., None])[..., 0]
    residual = (zu[solvable] - coeffs @ design) * v[solvable]
    rms = np.sqrt((residual**2).sum(axis=1) / v[solvable].sum(axis=1))

    out = np.full(grid.SHAPE, np.nan, dtype=np.float64)
    rows, cols = np.nonzero(usable)
    out[rows[solvable], cols[solvable]] = rms
    return out


def cell_terrain(
    fine_depth: np.ndarray, res_m: float, mine: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Slope (degrees) and roughness (metres) for the cells whose depth came from this raster.

    mine is the boolean grid of cells the merge took from this source; everywhere else
    is NaN.
    """
    sea = np.where(is_sea(fine_depth), fine_depth, np.nan)
    slope = grid.block_mean(slope_degrees(sea, res_m), min_fraction=0.5)
    rough = roughness(sea, min_fraction=0.5)
    return np.where(mine, slope, np.nan), np.where(mine, rough, np.nan)


# --- Chart soundings and contours to a surface --------------------------------------------


def thin(easting, northing, value, spacing_m: float = 50.0):
    """Average points that share a spacing_m square, so duplicates cannot break the mesh."""
    easting, northing, value = (np.asarray(a, dtype=np.float64) for a in (easting, northing, value))
    key = np.stack([np.floor(easting / spacing_m), np.floor(northing / spacing_m)], axis=1)
    _, index, counts = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    index = index.ravel()
    mean = lambda a: np.bincount(index, weights=a) / counts  # noqa: E731
    return mean(easting), mean(northing), mean(value)


def interpolate(easting, northing, value) -> np.ndarray:
    """Depth at every cell centre, linearly between the given points (a triangulated surface).

    NaN outside the hull of the points, and everywhere if there are fewer than three.
    """
    from scipy.interpolate import LinearNDInterpolator

    if len(value) < 3:
        return np.full(grid.SHAPE, np.nan)
    surface = LinearNDInterpolator(np.column_stack([easting, northing]), value)
    cell_e, cell_n = grid.centres()
    return surface(cell_e, cell_n)


def honour_soundings(surface: np.ndarray, soundings: np.ndarray) -> np.ndarray:
    """Give every cell that holds charted soundings their mean, in place of the interpolation.

    The triangulated surface is read at cell centres, so a lone shoal sounding off-centre
    can vanish between them. Where the chart has a measured depth inside a cell, that
    is the cell's depth. soundings is (n, 3): easting, northing, depth.
    """
    rows, cols = grid.cell_of(soundings[:, 0], soundings[:, 1])
    keep = grid.inside(rows, cols)
    index = rows[keep] * grid.NCOLS + cols[keep]
    total = np.bincount(index, weights=soundings[keep, 2], minlength=grid.NROWS * grid.NCOLS)
    count = np.bincount(index, minlength=grid.NROWS * grid.NCOLS)
    mean = (total / np.maximum(count, 1)).reshape(grid.SHAPE)
    return np.where(count.reshape(grid.SHAPE) > 0, mean, surface)


def clamp_to_depth_areas(depth: np.ndarray, shallowest: np.ndarray, deepest: np.ndarray):
    """Keep an interpolated depth inside the charted depth band of its cell.

    The chart's depth areas say, for every patch of water, the range the depth lies in
    (5 to 10 m, say). Interpolating across sparse soundings can drift out of that range;
    the band is the better evidence. NaN bounds leave the depth alone.
    """
    low = np.where(np.isnan(shallowest), -np.inf, shallowest)
    high = np.where(np.isnan(deepest), np.inf, deepest)
    return np.clip(depth, low, high)
