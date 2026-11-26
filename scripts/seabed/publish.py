"""Write the grids as the small static files the site loads.

One file per layer: the grid's values as unsigned integers, row by row from the north-west
corner, gzip-compressed. manifest.json says how to turn a stored integer back into a
value. Stored 0 always means "nothing here". web/src/seabed.ts is the reader; change
both sides together. The files are plain enough to read with the standard library too
(gzip, then array or struct), which the stage 2 pipeline on the server will do.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from seabed import grid


@dataclass(frozen=True)
class Scaling:
    """value = offset + scale * stored, for stored 1..max; stored 0 is no data."""

    dtype: str  # "uint8" or "uint16" (little-endian)
    scale: float
    offset: float

    @property
    def top(self) -> int:
        return int(np.iinfo(self.dtype).max)


# Depth to 0.1 m from 9.9 m above chart datum (well above any tide) down to 6,543 m.
DEPTH = Scaling("uint16", 0.1, -10.0)
# Slope to a quarter of a degree, 0 to 63.5; steeper is stored as 63.5.
SLOPE = Scaling("uint8", 0.25, -0.25)
# Roughness to 2 cm, 0 to 5.08 m; rougher is stored as 5.08.
ROUGHNESS = Scaling("uint8", 0.02, -0.02)
# Distance to the nearest reef to 25 m, 0 to 6,350 m; farther is stored as 6,350.
REEF_DISTANCE = Scaling("uint8", 25.0, -25.0)
# Distance to the mainland shore to 50 m, 0 to 12,700 m; farther is stored as 12,700.
SHORE_DISTANCE = Scaling("uint8", 50.0, -50.0)


def encode(values: np.ndarray, scaling: Scaling) -> np.ndarray:
    """Real values (NaN = no data) to stored integers, clipped to the range that fits."""
    stored = np.rint((values - scaling.offset) / scaling.scale)
    stored = np.clip(stored, 1, scaling.top)
    return np.where(np.isnan(values), 0, stored).astype(scaling.dtype)


def decode(stored: np.ndarray, scaling: Scaling) -> np.ndarray:
    """The inverse of encode, to the precision the scaling keeps."""
    values = scaling.offset + scaling.scale * stored.astype(np.float64)
    return np.where(stored == 0, np.nan, values)


def to_bytes(stored: np.ndarray, shape: tuple[int, int] = grid.SHAPE) -> bytes:
    """Gzip of the grid, row by row from the north-west, little-endian.

    mtime is fixed so the same grid always gives the same file, and git shows a change
    only when the data changed.
    """
    if stored.shape != shape:
        raise ValueError(f"grid of shape {stored.shape}, expected {shape}")
    raw = stored.astype(stored.dtype.newbyteorder("<")).tobytes()
    return gzip.compress(raw, compresslevel=9, mtime=0)


def from_bytes(data: bytes, dtype: str, shape: tuple[int, int] = grid.SHAPE) -> np.ndarray:
    raw = np.frombuffer(gzip.decompress(data), dtype=np.dtype(dtype).newbyteorder("<"))
    return raw.reshape(shape)


# --- The 20 m drawing grid ------------------------------------------------------------
#
# Twenty-five times the cells of the 100 m grid, so it is stored as what is left after
# guessing each cell from its neighbours: on a smooth seabed that is nearly nothing, and
# the file comes out at under half the size of the plain grid.

PREDICTOR = "plane"


def to_bytes_predicted(stored: np.ndarray, shape: tuple[int, int]) -> bytes:
    """Gzip of a uint16 grid, each cell stored as its difference from a prediction.

    The prediction is west + north - north-west (the plane through three neighbours;
    cells off the grid count as 0). The difference is taken modulo 65,536 as a signed
    16-bit number and folded to an unsigned one (0, -1, 1, -2 ... become 0, 1, 2, 3 ...),
    so small differences of either sign are small numbers. All the low bytes are written
    first, then all the high bytes, which are almost all zero.
    """
    if stored.shape != shape or stored.dtype != np.uint16:
        raise ValueError(f"expected a uint16 grid of shape {shape}")
    values = stored.astype(np.int64)
    predicted = np.zeros_like(values)
    predicted[:, 1:] += values[:, :-1]
    predicted[1:, :] += values[:-1, :]
    predicted[1:, 1:] -= values[:-1, :-1]
    difference = (values - predicted + 32768) % 65536 - 32768
    folded = np.where(difference >= 0, 2 * difference, -2 * difference - 1).astype(np.uint16)
    raw = (folded & 255).astype(np.uint8).tobytes() + (folded >> 8).astype(np.uint8).tobytes()
    return gzip.compress(raw, compresslevel=9, mtime=0)


def from_bytes_predicted(data: bytes, shape: tuple[int, int]) -> np.ndarray:
    """The inverse of to_bytes_predicted."""
    raw = np.frombuffer(gzip.decompress(data), dtype=np.uint8)
    cells = shape[0] * shape[1]
    folded = raw[:cells].astype(np.int64) | (raw[cells:].astype(np.int64) << 8)
    difference = np.where(folded % 2 == 0, folded // 2, -(folded + 1) // 2).reshape(shape)
    # Each difference is a cell minus its west and north neighbours plus the north-west
    # one, so summing along both axes gives the cells back.
    return (difference.cumsum(axis=0).cumsum(axis=1) % 65536).astype(np.uint16)


def scaled_layer(scaling: Scaling, **described) -> dict:
    return {"dtype": scaling.dtype, "scale": scaling.scale, "offset": scaling.offset, **described}


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n")


# --- Contours -------------------------------------------------------------------------


def smooth(values: np.ndarray, sigma_cells: float = 1.0) -> np.ndarray:
    """Gaussian smoothing that ignores NaN and leaves NaN where it was.

    Used only to draw contour lines that are not stair-stepped; the published depth grid
    is never smoothed.
    """
    from scipy.ndimage import gaussian_filter

    valid = ~np.isnan(values)
    total = gaussian_filter(np.where(valid, values, 0.0), sigma_cells, mode="nearest")
    weight = gaussian_filter(valid.astype(np.float64), sigma_cells, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(valid, total / weight, np.nan)


def simplify(line: np.ndarray, tolerance_m: float) -> np.ndarray:
    """Douglas-Peucker: drop vertices that sit within tolerance_m of the simplified line."""
    keep = np.zeros(len(line), dtype=bool)
    keep[[0, -1]] = True
    stack = [(0, len(line) - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        start, end = line[first], line[last]
        chord = end - start
        length = np.hypot(*chord)
        between = line[first + 1 : last] - start
        if length == 0:
            distance = np.hypot(between[:, 0], between[:, 1])
        else:
            distance = np.abs(chord[0] * between[:, 1] - chord[1] * between[:, 0]) / length
        worst = int(distance.argmax())
        if distance[worst] > tolerance_m:
            middle = first + 1 + worst
            keep[middle] = True
            stack += [(first, middle), (middle, last)]
    return line[keep]


def contours(
    depth: np.ndarray,
    levels,
    to_lonlat,
    tolerance_m: float = 15.0,
    min_length_m: float = 600.0,
    sigma_cells: float = 1.0,
) -> dict:
    """Depth contours of a depth grid as GeoJSON lines in longitude and latitude.

    depth covers the whole grid at any cell size that nests in it (the 100 m grid or the
    20 m drawing grid). to_lonlat(easting, northing) -> (lon, lat) arrays. The grid is
    smoothed by sigma_cells first (0 for none), so the lines are not stair-stepped, and
    lines shorter than min_length_m are dropped: they are noise, not seabed features.
    """
    from contourpy import contour_generator

    rows, cols = depth.shape
    cell_m = grid.CELL_M * grid.NROWS / rows
    cell_e = grid.WEST_E + (np.arange(cols) + 0.5) * cell_m
    cell_n = grid.NORTH_N - (np.arange(rows) + 0.5) * cell_m
    surface = np.ma.masked_invalid(smooth(depth, sigma_cells) if sigma_cells else depth)
    generator = contour_generator(x=cell_e, y=cell_n, z=surface)
    features = []
    for level in levels:
        for line in generator.lines(level):
            length = np.hypot(*np.diff(line, axis=0).T).sum()
            if length < min_length_m:
                continue
            line = simplify(line, tolerance_m)
            lon, lat = to_lonlat(line[:, 0], line[:, 1])
            coordinates = [
                [round(float(x), 5), round(float(y), 5)] for x, y in zip(lon, lat, strict=True)
            ]
            features.append(
                {
                    "type": "Feature",
                    "properties": {"depth": level},
                    "geometry": {"type": "LineString", "coordinates": coordinates},
                }
            )
    return {"type": "FeatureCollection", "features": features}
