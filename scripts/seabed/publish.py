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


def encode(values: np.ndarray, scaling: Scaling) -> np.ndarray:
    """Real values (NaN = no data) to stored integers, clipped to the range that fits."""
    stored = np.rint((values - scaling.offset) / scaling.scale)
    stored = np.clip(stored, 1, scaling.top)
    return np.where(np.isnan(values), 0, stored).astype(scaling.dtype)


def decode(stored: np.ndarray, scaling: Scaling) -> np.ndarray:
    """The inverse of encode, to the precision the scaling keeps."""
    values = scaling.offset + scaling.scale * stored.astype(np.float64)
    return np.where(stored == 0, np.nan, values)


def to_bytes(stored: np.ndarray) -> bytes:
    """Gzip of the grid, row by row from the north-west, little-endian.

    mtime is fixed so the same grid always gives the same file, and git shows a change
    only when the data changed.
    """
    if stored.shape != grid.SHAPE:
        raise ValueError(f"grid of shape {stored.shape}, expected {grid.SHAPE}")
    raw = stored.astype(stored.dtype.newbyteorder("<")).tobytes()
    return gzip.compress(raw, compresslevel=9, mtime=0)


def from_bytes(data: bytes, dtype: str) -> np.ndarray:
    raw = np.frombuffer(gzip.decompress(data), dtype=np.dtype(dtype).newbyteorder("<"))
    return raw.reshape(grid.SHAPE)


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
    depth: np.ndarray, levels, to_lonlat, tolerance_m: float = 15.0, min_length_m: float = 600.0
) -> dict:
    """Depth contours of the merged grid as GeoJSON lines in longitude and latitude.

    to_lonlat(easting, northing) -> (lon, lat) arrays. Lines shorter than min_length_m
    are dropped: at 100 m cells they are noise, not seabed features.
    """
    from contourpy import contour_generator

    cell_e, cell_n = grid.centres()
    surface = np.ma.masked_invalid(smooth(depth))
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
