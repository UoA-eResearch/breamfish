"""Read and write the byte grids of the seabed and habitat layers.

A layer is one file: the grid's values as unsigned integers, row by row from the
north-west corner, little-endian, gzip-compressed. Stored 0 always means "nothing
here"; otherwise value = offset + scale * stored, with the scale and offset given in
the layer's entry in manifest.json. The writers are scripts/seabed/publish.py (with
numpy, on a development machine) and this module (standard library only, so the same
code can run on the server). docs/seabed.md describes the format.
"""

from __future__ import annotations

import gzip
import json
import sys
from array import array
from dataclasses import dataclass
from pathlib import Path

_TYPECODE = {"uint8": "B", "uint16": "H"}


@dataclass(frozen=True)
class Grid:
    """Where the cells are. Rows run north to south, cells west to east."""

    west_e: float
    north_n: float
    cell_m: float
    ncols: int
    nrows: int

    @property
    def cells(self) -> int:
        return self.ncols * self.nrows

    def cell_of(self, easting: float, northing: float) -> int | None:
        """Index of the cell containing a point in NZTM, or None outside the grid."""
        col = int((easting - self.west_e) // self.cell_m)
        row = int((self.north_n - northing) // self.cell_m)
        if 0 <= col < self.ncols and 0 <= row < self.nrows:
            return row * self.ncols + col
        return None

    def centre(self, index: int) -> tuple[float, float]:
        """(easting, northing) of a cell's centre."""
        row, col = divmod(index, self.ncols)
        return (
            self.west_e + (col + 0.5) * self.cell_m,
            self.north_n - (row + 0.5) * self.cell_m,
        )


def grid_of(manifest: dict) -> Grid:
    g = manifest["grid"]
    return Grid(g["west_e"], g["north_n"], g["cell_m"], g["ncols"], g["nrows"])


def load_manifest(directory: Path) -> dict:
    return json.loads((directory / "manifest.json").read_text())


def read_stored(path: Path, dtype: str, cells: int) -> array:
    """The stored integers of one layer."""
    values = array(_TYPECODE[dtype])
    values.frombytes(gzip.decompress(path.read_bytes()))
    if sys.byteorder == "big":
        values.byteswap()
    if len(values) != cells:
        raise ValueError(f"{path.name}: {len(values)} cells, expected {cells}")
    return values


def read_scaled(directory: Path, layer: dict, cells: int) -> list[float | None]:
    """A measured layer as real values, None where there is nothing."""
    scale, offset = layer["scale"], layer["offset"]
    stored = read_stored(directory / layer["file"], layer["dtype"], cells)
    return [None if s == 0 else offset + scale * s for s in stored]


def write_stored(path: Path, values: array) -> None:
    """Write one layer. The same values always give the same file (no timestamp inside),
    so git shows a change only when the data changed."""
    if sys.byteorder == "big":
        values = array(values.typecode, values)
        values.byteswap()
    path.write_bytes(gzip.compress(values.tobytes(), compresslevel=9, mtime=0))
