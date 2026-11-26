"""Reading and writing the byte grids with the standard library alone."""

import gzip
import json
from array import array
from pathlib import Path

import pytest

from breamfish import grids

SEABED = Path(__file__).parent.parent / "web" / "public" / "seabed"


def test_a_layer_survives_the_round_trip_and_is_the_same_file_every_time(tmp_path):
    values = array("H", [0, 1, 258, 65535])
    grids.write_stored(tmp_path / "a.bin.gz", values)
    grids.write_stored(tmp_path / "b.bin.gz", values)
    assert (tmp_path / "a.bin.gz").read_bytes() == (tmp_path / "b.bin.gz").read_bytes()
    assert (
        gzip.decompress((tmp_path / "a.bin.gz").read_bytes())[4:6] == b"\x02\x01"
    )  # low byte first
    assert grids.read_stored(tmp_path / "a.bin.gz", "uint16", 4) == values
    with pytest.raises(ValueError):
        grids.read_stored(tmp_path / "a.bin.gz", "uint16", 5)


def test_stored_zero_is_nothing_and_the_rest_is_scaled(tmp_path):
    grids.write_stored(tmp_path / "depth.bin.gz", array("H", [0, 100, 335]))
    layer = {"file": "depth.bin.gz", "dtype": "uint16", "scale": 0.1, "offset": -10.0}
    assert grids.read_scaled(tmp_path, layer, 3) == [None, pytest.approx(0.0), pytest.approx(23.5)]


def test_cells_are_counted_from_the_north_west():
    grid = grids.Grid(west_e=1000.0, north_n=5000.0, cell_m=100.0, ncols=4, nrows=3)
    assert grid.cells == 12
    assert grid.cell_of(1000.0, 4999.9) == 0
    assert grid.cell_of(1399.9, 4700.1) == 11
    assert grid.cell_of(999.9, 4950) is None and grid.cell_of(1050, 4699.9) is None
    assert grid.centre(5) == (1150.0, 4850.0)
    assert grid.cell_of(*grid.centre(5)) == 5


def test_the_published_seabed_grids_read_as_the_manifest_describes():
    """The grids numpy wrote (scripts/seabed/publish.py) read back here without it."""
    manifest = grids.load_manifest(SEABED)
    grid = grids.grid_of(manifest)
    assert json.loads((SEABED / "manifest.json").read_text())["grid"]["ncols"] == grid.ncols
    layers = manifest["layers"]
    source = grids.read_stored(SEABED / layers["depth_source"]["file"], "uint8", grid.cells)
    depth = grids.read_scaled(SEABED, layers["depth"], grid.cells)
    counted = {c["code"]: c["cells"] for c in layers["depth_source"]["classes"]}
    for code, cells in counted.items():
        assert sum(1 for s in source if s == code) == cells
    # Every cell with a source has a depth, and no other cell does.
    assert all((s != 0) == (d is not None) for s, d in zip(source, depth, strict=True))
    reef = grids.read_scaled(SEABED, layers["reef_distance"], grid.cells)
    kinds = grids.read_stored(SEABED / layers["bottom"]["file"], "uint8", grid.cells)
    rock = next(c["code"] for c in layers["bottom"]["classes"] if c["key"] == "rock")
    assert all(r == 0 for r, k, s in zip(reef, kinds, source, strict=True) if k == rock and s)
