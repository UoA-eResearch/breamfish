"""Shaded relief and rough ground: the pieces, then the whole build on a made-up scene.

No network, no key. The scene, in 100 m cells (row, column):

    rows 40-59, columns 40-49   LiDAR: a smooth slope, 10 m deepening to 30 m eastwards
    rows 40-59, columns 50-59   LiDAR: flat sand at 20 m, with a ledge 5 m high on it
                                 and, south of the ledge, a bank 1 m high and 160 m wide
    rows 20-39, columns 55-79   multibeam: flat at 40 m with a ridge 6 m high; its south
                                 edge is under the LiDAR's north edge for one row of cells
    rows 40-44, columns 50-59   multibeam as well, under the LiDAR
    everywhere else             water the chart alone covers
"""

import json

import numpy as np
import pytest

import build_relief
import build_seabed
from seabed import bottom, depth, grid, publish, relief, report, sources, tiles

# A tile is a picture with no place on the earth of its own; rasterio says so each time.
pytestmark = pytest.mark.filterwarnings("ignore:Dataset has no geotransform")

# --- Shading ----------------------------------------------------------------------------


def plane(down_east: float = 0.0, down_north: float = 0.0, size: int = 40, res_m: int = 2):
    """Depths of a plane that deepens by these gradients towards the east and the north."""
    rows, cols = np.mgrid[0:size, 0:size]
    return 20.0 + down_east * cols * res_m - down_north * rows * res_m


def test_level_ground_has_no_shade():
    shaded = relief.shade(plane(), 2)
    assert shaded[5:-5, 5:-5] == pytest.approx(0.0, abs=1e-4)
    assert (relief.pixels(relief.to_stored(shaded)) == 0).all()


def test_a_face_towards_the_north_west_is_lit_and_one_away_from_it_is_in_shadow():
    # Deepening to the north-west: the ground falls away towards the light, and faces it.
    towards = relief.shade(plane(down_east=-0.02, down_north=0.02), 2)[20, 20]
    away = relief.shade(plane(down_east=0.02, down_north=-0.02), 2)[20, 20]
    assert towards > 0.05 and away < -0.05
    # On gentle ground a shadow is about as strong as a highlight.
    lit = relief.shade(plane(down_north=0.0125), 2)[20, 20]
    shadow = relief.shade(plane(down_north=-0.0125), 2)[20, 20]
    assert 0.08 < lit < 0.15 and shadow == pytest.approx(-lit, rel=0.25)
    # A steep face turned from the light is dark, and a steeper one a little darker
    # still: deep shadow is not all one black.
    steep = relief.shade(plane(down_east=0.1, down_north=-0.1), 2)[20, 20]
    steeper = relief.shade(plane(down_east=0.3, down_north=-0.3), 2)[20, 20]
    assert -1 < steeper < steep < -0.9


def test_shade_needs_depth_on_every_side():
    fine = plane(down_east=0.02)
    fine[10, 10] = np.nan
    shaded = relief.shade(fine, 2)
    for row, col in [(10, 10), (9, 10), (11, 10), (10, 9), (10, 11), (0, 5), (5, 0)]:
        assert np.isnan(shaded[row, col])
    assert not np.isnan(shaded[20, 20])
    assert relief.to_stored(shaded)[10, 10] == relief.NO_SHADE


def test_a_block_with_its_halo_is_shaded_as_the_whole_would_be():
    rng = np.random.default_rng(1)
    fine = 20 + np.cumsum(rng.normal(0, 0.05, (120, 120)), axis=1)
    halo = relief.halo_cells(2)
    whole = relief.shade(fine, 2)
    block = relief.shade(fine[40 - halo : 80 + halo, 40 - halo : 80 + halo], 2)
    assert block[halo:-halo, halo:-halo] == pytest.approx(whole[40:80, 40:80], abs=1e-4)


def test_only_lidar_sea_down_to_its_trusted_depth_is_shaded():
    height = np.array([[5.0, depth.CD_NZVD2016_M - 10, depth.CD_NZVD2016_M - 45, np.nan]])
    assert np.isnan(relief.lidar_sea(height, 40.0)[0, [0, 2, 3]]).all()  # dune, too deep, none
    assert relief.lidar_sea(height, 40.0)[0, 1] == pytest.approx(10.0)


def test_weak_shade_is_left_out_and_the_rest_is_black_or_white():
    stored = np.array([[relief.NO_SHADE, 0, 9, -9, 127, -127, 60]], dtype=np.int8)
    image = relief.pixels(stored)
    assert list(image[0, :4]) == [0, 0, 0, 0]  # nothing here, level, and under the floor
    assert image[0, 4] == 2 * relief.STEPS and image[0, 5] == relief.STEPS
    assert relief.PALETTE[int(image[0, 4])] == (255, 255, 255, 255)
    assert relief.PALETTE[int(image[0, 5])] == (0, 0, 0, 255)
    red, green, blue, alpha = relief.PALETTE[int(image[0, 6])]
    assert (red, green, blue) == (255, 255, 255) and 0 < alpha < 255


# --- Rough ground -----------------------------------------------------------------------


def test_a_smooth_slope_is_not_rough_and_a_ledge_is():
    rows, cols = np.mgrid[0:50, 0:50]
    slope = 10.0 + 0.3 * cols - 0.1 * rows
    assert relief.window_roughness(slope, 2) == pytest.approx(0.0, abs=1e-9)
    ledge = np.where(cols >= 22, 20.0, 15.0)  # a 5 m step through the middle of a window
    rough = relief.window_roughness(ledge, 2)
    assert rough.shape == (10, 10)
    assert rough[:, 4].min() > 1.0  # the windows the step runs through
    assert rough[:, [0, 1, 2, 3, 5, 6, 7, 8, 9]].max() == pytest.approx(0.0, abs=1e-9)


def test_a_window_mostly_without_depth_has_no_roughness():
    fine = np.full((5, 10), 20.0)
    fine[:, :4] = np.nan  # the first window keeps one column of five
    fine[0, 5] = np.nan  # the second loses one cell of 25
    rough = relief.window_roughness(fine, 2)
    assert np.isnan(rough[0, 0]) and rough[0, 1] == pytest.approx(0.0)


def test_a_cell_scores_its_third_roughest_square():
    windows = np.full((grid.NROWS * 10, grid.NCOLS * 10), np.nan, dtype=np.float32)
    windows[0:10, 0:10] = 0.02  # cell (0, 0): sand, with three rough squares
    windows[0, 0:3] = (0.9, 0.5, 0.3)
    windows[10:20, 0:4] = 0.04  # cell (1, 0): under half of it has LiDAR
    windows[0:10, 10:20] = 0.02  # cell (0, 1): sand, and one stray return
    windows[5, 15] = 2.0
    cells = relief.cell_roughness(windows)
    assert cells[0, 0] == pytest.approx(0.3)
    assert cells[0, 1] == pytest.approx(0.02)
    assert np.isnan(cells[1, 0]) and np.isnan(cells[5, 5])


def test_auc_is_the_chance_a_rock_cell_scores_higher():
    score = np.array([0.5, 0.4, 0.1, 0.1, 0.05, np.nan])
    rock = np.array([True, True, True, False, False, True])
    assert report.auc(score, rock, ~rock) == pytest.approx((2 + 2 + 1.5) / 6, abs=1e-3)
    assert report.auc(score, rock, np.zeros(6, dtype=bool)) is None


# --- Tiles ------------------------------------------------------------------------------


def test_a_coarser_tile_is_the_mean_of_the_four_pixels_under_each_of_its_own():
    child = np.full((tiles.TILE_PX, tiles.TILE_PX), relief.NO_SHADE, dtype=np.int8)
    child[0:2, 0:2] = [[10, 20], [30, 40]]  # all four: their mean
    child[0:2, 2:4] = [[100, relief.NO_SHADE], [-50, relief.NO_SHADE]]  # two of four
    child[0, 4] = 80  # one of four: the survey's edge does not grow
    parents = tiles.coarser({(6, 4): child})
    assert list(parents) == [(3, 2)]
    parent = parents[(3, 2)]
    assert (parent[0, 0], parent[0, 1], parent[0, 2]) == (25, 25, relief.NO_SHADE)
    assert (parent[:, tiles.TILE_PX // 2 :] == relief.NO_SHADE).all()  # no child there
    # One pixel with shade is not two of four: a zoom out, it is gone.
    lone = np.full((tiles.TILE_PX, tiles.TILE_PX), relief.NO_SHADE, dtype=np.int8)
    lone[100, 100] = 80
    assert tiles.coarser({(6, 4): lone}) == {}


def test_a_tile_is_a_png_with_the_palette_and_an_empty_one_is_not_written():
    from rasterio.io import MemoryFile

    stored = np.full((tiles.TILE_PX, tiles.TILE_PX), relief.NO_SHADE, dtype=np.int8)
    assert tiles.png(stored) is None
    stored[:] = 3  # shade, but under the floor
    assert tiles.png(stored) is None
    stored[10, 20], stored[10, 21] = 127, -127
    data = tiles.png(stored)
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and data == tiles.png(stored)
    with MemoryFile(data) as memory, memory.open() as picture:
        image, colours = picture.read(1), picture.colormap(1)
    assert colours[int(image[10, 20])] == (255, 255, 255, 255)
    assert colours[int(image[10, 21])] == (0, 0, 0, 255)
    assert colours[int(image[0, 0])][3] == 0 and int(image.max()) == 2 * relief.STEPS


# --- Fetching ---------------------------------------------------------------------------


def test_lidar_at_another_resolution_is_cached_under_its_own_names(tmp_path, monkeypatch):
    def no_network():
        raise AssertionError("a test reached for the network")

    for survey, sheets in sources.LIDAR_TILES:
        for sheet in sheets:
            name = f"{survey.split('/')[1]}_{sheet}"
            (tmp_path / "lidar").mkdir(exist_ok=True)
            (tmp_path / "lidar" / f"{name}.tiff").touch()
            (tmp_path / "lidar" / f"{name}_2m.tiff").touch()
    coarse = sources.lidar_paths(tmp_path)
    fine = sources.lidar_paths(tmp_path, 2)
    assert len(coarse) == len(fine) == 5
    assert all(not p.name.endswith("_2m.tiff") for p in coarse)  # the names they always had
    assert all(p.name.endswith("_2m.tiff") for p in fine)
    # Nothing is fetched when the cache is whole; a missing sheet would be.
    monkeypatch.setattr(sources, "_client", no_network)
    (tmp_path / "lidar" / fine[0].name).unlink()
    with pytest.raises(AssertionError):
        sources.lidar_paths(tmp_path, 2)


def test_one_block_of_a_tile_is_read_where_it_lies_on_the_grid(tmp_path):
    import rasterio
    from rasterio.transform import from_origin

    # A 2 m tile whose corner is 20 m west and 10 m north of the grid's own.
    values = np.arange(50 * 60, dtype=np.float32).reshape(50, 60)
    values[30, 40] = -9999.0
    path = tmp_path / "tile.tiff"
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=60,
        height=50,
        count=1,
        dtype="float32",
        crs="EPSG:2193",
        transform=from_origin(grid.WEST_E - 20, grid.NORTH_N + 10, 2, 2),
        nodata=-9999.0,
    ) as tile:
        tile.write(values, 1)
    block = sources.mosaic([path], 2, (0, 0, 10, 10))
    assert block[0, 0] == values[5, 10] and block[9, 9] == values[14, 19]
    # A window may start past the grid's edge, to carry a halo; and run off the tile.
    halo = sources.mosaic([path], 2, (-5, -10, 60, 80))
    assert halo[0, 0] == values[0, 0] and halo[49, 59] == values[49, 59]
    assert np.isnan(halo[30, 40]) and np.isnan(halo[55, 70])
    with pytest.raises(ValueError, match="expected EPSG:2193 at 10 m"):
        sources.mosaic([path], 10)


# --- The whole build on a made-up scene ---------------------------------------------------

LIDAR_ROWS, LIDAR_COLS = (40, 60), (40, 60)  # in 100 m cells
LEDGE = (2402, 2602, 2702, 2902)  # in 2 m cells: north, south, west, east edge of its top
BANK = (2700, 2740, 2780)  # in 2 m cells: the rows of its north foot, its crest, its south foot
RIDGE_ROW = 150  # in 20 m cells
CHARTED = (100, 100)  # a 100 m cell of water the chart alone covers


def lidar_patch():
    """NZVD2016 heights of the LiDAR's part of the scene, in 2 m cells, and where it sits."""
    rows, cols = np.mgrid[2000:3000, 2000:3000]
    fine = np.where(cols < 2500, 10.0 + 0.04 * (cols - 2000), 20.0)
    north, south, west, east = LEDGE
    fine[(rows >= north) & (rows < south) & (cols >= west) & (cols < east)] = 15.0
    foot, crest, _ = BANK
    on_bank = (cols >= 2550) & (cols < 2950)
    fine = fine - np.where(on_bank, np.clip(1 - np.abs(rows - crest) / (crest - foot), 0, 1), 0)
    return (depth.CD_NZVD2016_M - fine).astype(np.float32), (2000, 2000)


def reader(patch: np.ndarray, corner: tuple[int, int]):
    """A patch of LiDAR as build_relief reads it: any window of the 2 m grid, NaN elsewhere."""

    def read(window):
        top, left, rows, cols = window
        out = np.full((rows, cols), np.nan, dtype=np.float32)
        r_lo, r_hi = max(top, corner[0]), min(top + rows, corner[0] + patch.shape[0])
        c_lo, c_hi = max(left, corner[1]), min(left + cols, corner[1] + patch.shape[1])
        if r_lo < r_hi and c_lo < c_hi:
            out[r_lo - top : r_hi - top, c_lo - left : c_hi - left] = patch[
                r_lo - corner[0] : r_hi - corner[0], c_lo - corner[1] : c_hi - corner[1]
            ]
        return out

    return read


def scene() -> build_relief.Inputs:
    multibeam = np.full(grid.fine_shape(20), np.nan, dtype=np.float32)
    multibeam[100:200, 275:400] = -40.0
    rows = np.arange(100, 200)[:, None]
    multibeam[100:200, 275:400] += 6.0 * np.exp(-(((rows - RIDGE_ROW) / 4.0) ** 2))
    multibeam[200:225, 250:300] = -20.0  # under the LiDAR, where the LiDAR is drawn

    source = np.full(grid.SHAPE, depth.CHART_OLD.code, dtype=np.uint8)
    source[20:40, 55:80] = depth.MULTIBEAM.code
    source[slice(*LIDAR_ROWS), slice(*LIDAR_COLS)] = depth.LIDAR.code
    kind = np.full(grid.SHAPE, bottom.SOFT, dtype=np.uint8)
    kind_source = np.full(grid.SHAPE, bottom.HABITAT_MAP, dtype=np.uint8)
    kind[48:52, 54:58], kind_source[48:52, 54:58] = bottom.ROCK, bottom.CHART_ROCK  # the ledge
    kind[44:48, 52], kind_source[44:48, 52] = bottom.SAND, bottom.CHART_SAMPLE  # flat sand
    return build_relief.Inputs(
        lidar=reader(*lidar_patch()),
        multibeam_fine=multibeam,
        cell_source=source,
        depth=np.full(grid.SHAPE, 20.0),
        bottom=kind,
        bottom_source=kind_source,
        roughness=np.full(grid.SHAPE, 0.05),
        slope=np.full(grid.SHAPE, 0.5),
    )


@pytest.fixture(scope="module")
def built():
    return build_relief.build(scene())


def shade_at(levels: dict, zoom: int, row: float, col: float, cell_m: int):
    """The stored shade a pyramid holds at a point given in cells of cell_m; None if no tile."""
    easting = grid.WEST_E + col * cell_m
    northing = grid.NORTH_N - row * cell_m
    lon, lat = build_seabed.to_lonlat(easting, northing)
    world = 2**zoom
    x = (lon[0] + 180) / 360 * world
    y = (1 - np.arcsinh(np.tan(np.radians(lat[0]))) / np.pi) / 2 * world
    tile = levels[zoom].get((int(x), int(y)))
    if tile is None:
        return None
    return int(tile[int((y % 1) * tiles.TILE_PX), int((x % 1) * tiles.TILE_PX)])


def test_measured_ground_is_lit_towards_the_light_and_dark_away_from_it(built):
    zoom = build_relief.LIDAR_MAX_ZOOM
    foot, crest, far_foot = BANK
    assert shade_at(built.lidar_tiles, zoom, (foot + crest) / 2, 2750, 2) > 8  # faces north
    assert shade_at(built.lidar_tiles, zoom, (crest + far_foot) / 2, 2750, 2) < -8
    # The ledge is a wall 5 m high: too steep to face a light 45 degrees up, so both of
    # its sides are dark, the one turned from the light the darker.
    north, south, west, east = LEDGE
    middle = (west + east) / 2
    assert shade_at(built.lidar_tiles, zoom, south, middle, 2) < -110
    assert -110 < shade_at(built.lidar_tiles, zoom, north, middle, 2) < -8
    # On top of it, and on the sand beside it, there is ground and no shade.
    assert shade_at(built.lidar_tiles, zoom, (north + south) / 2, middle, 2) == 0
    assert shade_at(built.lidar_tiles, zoom, 2300, 2600, 2) == 0
    # The smooth slope deepens to the east, away from the light: an even, weak shadow.
    assert -40 < shade_at(built.lidar_tiles, zoom, 2500, 2250, 2) < 0


def test_water_that_is_only_charted_is_not_shaded(built):
    row, col = CHARTED
    for levels, top in (
        (built.lidar_tiles, build_relief.LIDAR_MAX_ZOOM),
        (built.multibeam_tiles, build_relief.MULTIBEAM_MAX_ZOOM),
    ):
        assert set(levels) == set(range(build_relief.MIN_ZOOM, top + 1))
        for zoom in levels:
            assert shade_at(levels, zoom, row + 0.5, col + 0.5, 100) in (None, relief.NO_SHADE)
    # Nor is the LiDAR's shade drawn beyond the LiDAR.
    assert shade_at(built.lidar_tiles, 16, 2500, 1990, 2) in (None, relief.NO_SHADE)
    assert shade_at(built.lidar_tiles, 16, 2500, 3010, 2) in (None, relief.NO_SHADE)


def test_the_multibeam_is_shaded_where_the_lidar_is_not(built):
    zoom = build_relief.MULTIBEAM_MAX_ZOOM
    assert shade_at(built.multibeam_tiles, zoom, RIDGE_ROW - 3, 340, 20) > 20  # faces north
    assert shade_at(built.multibeam_tiles, zoom, RIDGE_ROW + 3, 340, 20) < -20
    assert shade_at(built.multibeam_tiles, zoom, 120, 340, 20) == 0  # flat, and measured
    # The multibeam under the LiDAR is left to the LiDAR; beside it, it is drawn.
    assert shade_at(built.multibeam_tiles, zoom, 212, 262, 20) in (None, relief.NO_SHADE)
    assert shade_at(built.lidar_tiles, 14, 2120, 2620, 2) == 0


def test_shade_survives_to_the_widest_zoom(built):
    for zoom in range(build_relief.MIN_ZOOM, build_relief.LIDAR_MAX_ZOOM + 1):
        assert shade_at(built.lidar_tiles, zoom, 2300, 2600, 2) is not None, zoom
    # Two zooms out a pixel is four across: the bank's flanks are still told apart.
    foot, crest, far_foot = BANK
    assert shade_at(built.lidar_tiles, 14, (foot + crest) / 2, 2750, 2) > 8
    assert shade_at(built.lidar_tiles, 14, (crest + far_foot) / 2, 2750, 2) < -8


def test_rough_ground_is_high_on_the_ledge_and_near_zero_on_the_smooth_slope(built):
    rough = built.fine_roughness
    assert rough[48, 55] > 0.5  # the ledge's north edge runs through this cell
    assert rough[50, 44] == pytest.approx(0.0, abs=1e-4)  # the slope
    assert rough[45, 52] == pytest.approx(0.0, abs=1e-4)  # flat sand
    assert rough[54, 55] < 0.05  # the bank: a metre high, and smooth
    # Only where the depth is the LiDAR's.
    lidar = np.zeros(grid.SHAPE, dtype=bool)
    lidar[slice(*LIDAR_ROWS), slice(*LIDAR_COLS)] = True
    assert not np.isnan(rough[lidar]).any() and np.isnan(rough[~lidar]).all()


def test_the_report_scores_rough_ground_against_the_charted_bottom(built):
    rough = built.facts["rough_ground"]
    assert rough["cells"] == 400
    assert rough["groups"]["chart_soft"]["cells"] == 4
    assert rough["groups"]["chart_soft"]["median_m"] == 0.0
    # Of the sixteen cells charted as rock, the ledge's edges run through seven. The
    # other nine are its flat top: charted as rock, and as smooth as the sand.
    assert rough["groups"]["chart_rock"]["cells"] == 16
    assert rough["thresholds"][0]["chart_rock"] == 7 and rough["thresholds"][0]["chart_soft"] == 0
    by_measure = {row["measure"]: row for row in rough["auc"]}
    assert by_measure[report.PUBLISHED_MEASURE]["chart"] == pytest.approx(
        (7 + 9 / 2) / 16, abs=1e-3
    )
    assert by_measure[report.GRID_ROUGHNESS_MEASURE]["chart"] == 0.5  # the same everywhere
    assert built.facts["shaded_km2"]["lidar"] == pytest.approx(4.0, abs=0.1)

    text = report.rough_ground_markdown(built.facts)
    assert text.startswith(report.ROUGH_GROUND_HEADING)
    assert "| Chart: marked as rock | 16 |" in text
    assert "It tells charted rock from charted sand and mud better than" in text
    assert "do not support overruling" in text


def test_the_two_surveys_are_compared_where_both_measured():
    lidar = np.full((40, 40), relief.NO_SHADE, dtype=np.int8)
    multibeam = np.full((4, 4), np.nan)
    assert report.shade_agreement(lidar, multibeam) == {"cells": 0}
    lidar[:, :] = np.repeat(np.repeat(np.arange(16).reshape(4, 4) * 8, 10, 0), 10, 1)
    multibeam[:, :] = np.arange(16).reshape(4, 4) / 16
    multibeam[0, 0] = np.nan
    lidar[30:40, 30:40] = relief.NO_SHADE
    agree = report.shade_agreement(lidar, multibeam)
    assert agree["cells"] == 14 and agree["correlation"] == pytest.approx(1.0)


def darkest(tile: np.ndarray) -> int:
    """How deep the deepest shadow in a tile of stored shade is."""
    return int(-np.where(tile == relief.NO_SHADE, 0, tile).min())


@pytest.fixture()
def seabed_dir(tmp_path):
    """A seabed directory as build_seabed.py leaves it, as far as this build reads it."""
    out = tmp_path / "seabed"
    out.mkdir()
    publish.write_json(
        out / "manifest.json",
        {"schema": 2, "built": "2026-01-01", "layers": {"depth": {"file": "depth.bin.gz"}}},
    )
    report_path = tmp_path / "report.md"
    report_path.write_text("# Seabed build report\n\nWhat the seabed build wrote.\n")
    return out, report_path


def test_written_files_match_what_the_manifest_says(built, seabed_dir, tmp_path):
    from pmtiles.reader import MmapSource, Reader
    from pmtiles.tile import TileType
    from rasterio.io import MemoryFile

    seabed, report_path = seabed_dir
    build_relief.write(built, tmp_path / "tiles", seabed, report_path)
    manifest = json.loads((seabed / "manifest.json").read_text())
    # The seabed build's part of the manifest is as it was.
    assert manifest["built"] == "2026-01-01" and manifest["schema"] == 2
    assert manifest["layers"]["depth"] == {"file": "depth.bin.gz"}

    layer = manifest["layers"]["fine_roughness"]
    stored = publish.from_bytes((seabed / layer["file"]).read_bytes(), layer["dtype"])
    assert layer["offset"] + layer["scale"] * stored[50, 44] == pytest.approx(0.0)
    assert layer["offset"] + layer["scale"] * stored[48, 55] > 0.5
    assert stored[CHARTED] == 0
    assert layer["bands_m"] == list(report.ROUGH_THRESHOLDS_M) and "0.10 m" in layer["reading"]

    described = manifest["relief"]
    assert described["exaggeration"] == relief.EXAGGERATION and "measured" in described["note"]
    assert [a["key"] for a in described["archives"]] == ["multibeam", "lidar"]
    for archive in described["archives"]:
        path = tmp_path / "tiles" / archive["url"].removeprefix("/tiles/")
        assert path.stat().st_size == archive["bytes"]
        assert archive["licence"] and archive["url_source"] and len(archive["version"]) == 12
        with path.open("rb") as file:
            archived = Reader(MmapSource(file))
            header = archived.header()
            assert header["tile_type"] == TileType.PNG
            assert (header["min_zoom"], header["max_zoom"]) == (
                archive["min_zoom"],
                archive["max_zoom"],
            )
            assert header["addressed_tiles_count"] == archive["tiles"]
            west, south, east, north = build_seabed.lonlat_bounds()
            assert header["min_lon_e7"] == round(west * 1e7)
            assert header["max_lat_e7"] == round(north * 1e7)
            if archive["key"] != "lidar":
                continue
            # The tile with the darkest shadow in it: nearly solid there, clear on the sand.
            zoom = archive["max_zoom"]
            (x, y), _ = max(built.lidar_tiles[zoom].items(), key=lambda item: darkest(item[1]))
            with MemoryFile(archived.get(zoom, x, y)) as memory, memory.open() as picture:
                image, colours = picture.read(1), picture.colormap(1)
            alpha = np.array([colours.get(i, (0, 0, 0, 0))[3] for i in range(256)])[image]
            assert alpha.max() > 230 and (alpha == 0).mean() > 0.5
            # A tile of nothing but level sand is not in the archive at all.
            flat = next(key for key, tile in built.lidar_tiles[zoom].items() if not tile.any())
            assert archived.get(zoom, *flat) is None

    text = report_path.read_text()
    assert text.startswith("# Seabed build report\n\nWhat the seabed build wrote.\n\n## Rough")
    # A second run replaces its own section and adds no second one.
    build_relief.write(built, tmp_path / "tiles", seabed, report_path)
    assert report_path.read_text() == text


def test_a_rebuild_gives_the_same_bytes(built, seabed_dir, tmp_path):
    seabed, report_path = seabed_dir
    build_relief.write(built, tmp_path / "first", seabed, report_path)
    again = build_relief.build(scene())
    build_relief.write(again, tmp_path / "second", seabed, report_path)
    names = (build_relief.LIDAR_ARCHIVE, build_relief.MULTIBEAM_ARCHIVE)
    for name in names:
        first = (tmp_path / "first" / name).read_bytes()
        assert first == (tmp_path / "second" / name).read_bytes(), name
        assert first[:7] == b"PMTiles"
    assert np.array_equal(built.fine_roughness, again.fine_roughness, equal_nan=True)


# --- What is committed --------------------------------------------------------------------

ROOT = build_relief.ROOT
PUBLIC = ROOT / "web" / "public"


def test_the_committed_relief_is_the_one_the_manifest_describes():
    """Rebuild the seabed and this fails until scripts/build_relief.py has been run again
    and its output committed with it."""
    import hashlib

    manifest = json.loads((PUBLIC / "seabed" / "manifest.json").read_text())
    for archive in manifest["relief"]["archives"]:
        data = (PUBLIC / archive["url"].removeprefix("/")).read_bytes()
        assert len(data) == archive["bytes"], archive["url"]
        assert hashlib.sha256(data).hexdigest()[:12] == archive["version"], archive["url"]

    layers = manifest["layers"]
    rough = publish.from_bytes(
        (PUBLIC / "seabed" / layers["fine_roughness"]["file"]).read_bytes(), "uint8"
    )
    source = publish.from_bytes(
        (PUBLIC / "seabed" / layers["depth_source"]["file"]).read_bytes(), "uint8"
    )
    assert (source[rough != 0] == depth.LIDAR.code).all(), "run scripts/build_relief.py again"
    # Nearly every LiDAR cell has it; the few without are less than half covered at 2 m.
    assert (rough != 0).sum() > 0.98 * (source == depth.LIDAR.code).sum()
    section = report.rough_ground_section((ROOT / "docs" / "seabed-report.md").read_text())
    assert f"{int((rough != 0).sum()):,} cells" in section
