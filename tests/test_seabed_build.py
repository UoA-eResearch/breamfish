"""The whole seabed build on made-up inputs: no network, no key, a few seconds.

The scene, in grid cells (row, column), is laid out so every rule has a place to show:

    columns   0-9    LiDAR sees dune (land)
    columns  10-99   LiDAR sees 5 m of water, except a corner where it reports 45 m
    columns  80-149  multibeam sees 30 m (so it overlaps the LiDAR in columns 80-99)
    columns   0-299  the chart covers rows 0-199: a 10 to 20 m depth area, soundings of
                     15 m, an island at columns 250-259, surveyed in 1962 west of column
                     200 and in 2010 east of it
    everywhere       the global grid says 50 m below mean sea level
"""

import json

import numpy as np
import pytest

import build_seabed
from seabed import bottom, depth, drawing, grid, publish


def box(col0, row0, col1, row1):
    """A GeoJSON polygon covering whole cells, columns col0..col1-1 and rows row0..row1-1."""
    west, east = grid.WEST_E + col0 * 100, grid.WEST_E + col1 * 100
    north, south = grid.NORTH_N - row0 * 100, grid.NORTH_N - row1 * 100
    ring = [[west, north], [east, north], [east, south], [west, south], [west, north]]
    return {"type": "Polygon", "coordinates": [ring]}


def feature(geometry, **properties):
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def point(row, col):
    easting, northing = grid.cell_centre(row, col)
    return {"type": "Point", "coordinates": [float(easting), float(northing)]}


@pytest.fixture(scope="module")
def built():
    lidar = np.full(grid.fine_shape(10), np.nan, dtype=np.float32)
    lidar[0:1000, 0:100] = 10.0  # dune
    lidar[0:1000, 100:1000] = depth.CD_NZVD2016_M - 5.0  # 5 m below chart datum
    lidar[0:100, 900:1000] = depth.CD_NZVD2016_M - 45.0  # deeper than LiDAR is trusted
    multibeam = np.full(grid.fine_shape(20), np.nan, dtype=np.float32)
    multibeam[0:500, 400:750] = -30.0

    band = build_seabed.ChartBand(
        name="test",
        depth_areas=[feature(box(0, 0, 300, 200), drval1=10, drval2=20)],
        soundings=[feature(point(r, c), depth=15.0) for r in (2, 100, 198) for c in (2, 160, 298)]
        + [feature(point(50, 50), depth=5.4), feature(point(50, 120), depth=29.0)],
        contours=[],
        land=[feature(box(250, 90, 260, 110))],
        quality=[
            feature(box(0, 0, 200, 200), surend="19621231", catzoc="4"),
            feature(box(200, 0, 300, 200), surend="20100315", catzoc="3"),
        ],
        seabed_points=[feature(point(150, 100), natsur="4,17")],
        seabed_polygons=[feature(box(100, 150, 102, 152), natsur="9")],
        rocks=[feature(point(150, 220))],
    )
    habitat = [feature(box(0, 0, grid.NCOLS, grid.NROWS), Substrate="soft sediments")]
    rows, cols = np.meshgrid(
        np.arange(2, grid.NROWS, 5), np.arange(2, grid.NCOLS, 5), indexing="ij"
    )
    easting, northing = grid.cell_centre(rows, cols)
    gebco = np.stack([easting, northing, np.full(easting.shape, -50.0)], axis=2)

    inputs = build_seabed.Inputs(lidar, multibeam, [band], habitat, gebco)
    return build_seabed.build(inputs)


def test_lidar_wins_where_it_has_water(built):
    grids, _ = built
    assert grids.source[50, 50] == depth.LIDAR.code
    assert grids.depth[50, 50] == pytest.approx(5.0, abs=1e-4)
    assert grids.source[50, 90] == depth.LIDAR.code  # multibeam is here too, and loses


def test_land_has_no_depth(built):
    grids, _ = built
    for row, col in [(50, 5), (100, 255)]:  # LiDAR dune, charted island
        assert grids.source[row, col] == 0
        assert np.isnan(grids.depth[row, col])
        assert grids.bottom[row, col] == bottom.UNKNOWN


def test_lidar_beyond_its_trusted_depth_gives_way_to_the_next_source(built):
    grids, facts = built
    assert facts["lidar_cells_dropped_as_too_deep"] == 100
    assert grids.source[5, 95] == depth.MULTIBEAM.code
    assert grids.depth[5, 95] == pytest.approx(30.0)
    assert grids.source[5, 120] == depth.MULTIBEAM.code


def test_chart_fills_the_rest_and_is_classed_by_survey_date(built):
    grids, _ = built
    assert grids.source[150, 100] == depth.CHART_OLD.code  # surveyed 1962
    assert grids.source[150, 280] == depth.CHART_RECENT.code  # surveyed 2010
    charted = grids.depth[np.isin(grids.source, [depth.CHART_OLD.code, depth.CHART_RECENT.code])]
    assert charted.min() >= 10 and charted.max() <= 20  # held inside the charted depth band


def test_a_charted_sounding_beats_the_depth_band_in_its_own_cell(built):
    grids, _ = built
    # The 15 m soundings sit in a 10 to 20 m band; one more, on a shoal, would too.
    assert grids.depth[100, 160] == pytest.approx(15.0)
    assert grids.source[100, 160] == depth.CHART_OLD.code


def test_the_global_grid_is_only_background(built):
    grids, _ = built
    assert grids.source[300, 300] == depth.BACKGROUND.code
    assert grids.depth[300, 300] == pytest.approx(50 - depth.MSL_M)
    # Inside the outermost soundings the chart has an answer, so the background is not used.
    assert not (grids.source[5:195, 5:295] == depth.BACKGROUND.code).any()


def test_slope_and_roughness_exist_only_on_surveyed_cells(built):
    grids, _ = built
    assert grids.slope[50, 50] == pytest.approx(0, abs=1e-6)
    assert grids.roughness[50, 120] == pytest.approx(0, abs=1e-6)
    surveyed = np.isin(grids.source, [depth.LIDAR.code, depth.MULTIBEAM.code])
    assert np.isnan(grids.slope[~surveyed]).all()
    assert np.isnan(grids.roughness[~surveyed]).all()
    # The LiDAR and multibeam surfaces differ by 25 m where they meet. No cell shows it.
    assert np.nanmax(grids.slope) < 1


def test_bottom_type_takes_the_most_specific_source(built):
    grids, _ = built
    assert (grids.bottom[150, 100], grids.bottom_source[150, 100]) == (
        bottom.ROCK,
        bottom.CHART_ROCK,
    )
    assert (grids.bottom[150, 220], grids.bottom_source[150, 220]) == (
        bottom.ROCK,
        bottom.CHART_ROCK,
    )
    assert (grids.bottom[300, 300], grids.bottom_source[300, 300]) == (
        bottom.SOFT,
        bottom.HABITAT_MAP,
    )


def fine(row, col):
    """The 20 m cell in the middle of a 100 m cell."""
    return row * drawing.FACTOR + 2, col * drawing.FACTOR + 2


def test_the_drawing_grid_shows_each_survey_where_it_has_water(built):
    grids, _ = built
    assert grids.drawing_depth.shape == grids.drawing_source.shape == drawing.SHAPE
    assert grids.drawing_source[fine(50, 50)] == depth.LIDAR.code
    assert grids.drawing_depth[fine(50, 50)] == pytest.approx(5.0, abs=1e-3)
    assert grids.drawing_source[fine(50, 120)] == depth.MULTIBEAM.code
    assert grids.drawing_depth[fine(50, 120)] == pytest.approx(30.0, abs=1e-3)
    # Too deep for the LiDAR here as well, so the multibeam shows through.
    assert grids.drawing_source[fine(5, 95)] == depth.MULTIBEAM.code


def test_the_drawing_grid_draws_charted_water_inside_its_depth_band(built):
    grids, _ = built
    assert grids.drawing_source[fine(150, 100)] == depth.CHART_OLD.code
    assert grids.drawing_source[fine(150, 280)] == depth.CHART_RECENT.code
    # Well inside the charted water, away from the surveys and the island.
    patch = grids.drawing_depth[120 * 5 : 180 * 5, 160 * 5 : 240 * 5]
    assert patch.min() >= 10 and patch.max() <= 20
    # Beyond the outermost sounding (row 198) the chart's depth band still holds. The
    # 48 m of the global grid starts at row 200, and without the band this would be 40.
    assert grids.drawing_depth[199 * 5, 150 * 5] == pytest.approx(20, abs=0.05)


def test_the_drawing_grid_runs_a_little_past_the_shore_and_says_so(built):
    grids, _ = built
    row = fine(50, 0)[0]
    shore = 10 * drawing.FACTOR  # the LiDAR's dune ends here
    assert grids.drawing_source[row, shore] == depth.LIDAR.code
    fringe = grids.drawing_source[row, shore - int(drawing.BLEED_CELLS) : shore]
    assert (fringe == depth.LIDAR.code + drawing.PAST_SHORE).all()
    assert grids.drawing_depth[row, shore - 1] == pytest.approx(5.0, abs=1e-3)
    assert grids.drawing_source[row, shore - int(drawing.BLEED_CELLS) - 1] == 0
    assert np.isnan(grids.drawing_depth[row, 0])
    # The charted island: land in the middle, a fringe at its edge.
    assert grids.drawing_source[fine(100, 255)] == 0
    assert grids.drawing_source[fine(100, 250)] == depth.CHART_RECENT.code + drawing.PAST_SHORE


def test_the_drawing_grid_keeps_outlines_and_draws_point_notes_as_dots(built):
    grids, _ = built
    # The rock area is two cells square on the chart, and that is what is drawn.
    rock = grids.drawing_bottom == bottom.ROCK
    area = rock[150 * 5 : 152 * 5, 100 * 5 : 102 * 5]
    assert area.all()
    assert (grids.drawing_bottom_source[150 * 5 : 152 * 5, 100 * 5 : 102 * 5] == 1).all()
    # A charted rock is a mark at a point: the middle of its cell, not the corners.
    assert grids.drawing_bottom[fine(150, 220)] == bottom.ROCK
    assert grids.drawing_bottom[150 * 5, 220 * 5] == bottom.SOFT
    assert grids.drawing_bottom_source[150 * 5, 220 * 5] == bottom.HABITAT_MAP
    # Nothing is classed on land.
    assert grids.drawing_bottom[fine(100, 255)] == bottom.UNKNOWN


def test_the_checks_against_soundings_are_reported(built):
    _, facts = built
    lidar = facts["lidar_check"]
    assert lidar and lidar[0]["soundings"] == 1 and lidar[0]["median_m"] == pytest.approx(-0.4)
    by_survey = facts["lidar_check_by_survey"]
    assert by_survey[0] == {
        "survey": "1955 to 1962",
        "ground": "all",
        "soundings": 1,
        "median_m": -0.4,
        "quartiles_m": [-0.4, -0.4],
    }
    assert by_survey[1]["ground"] == "flat" and by_survey[1]["soundings"] == 1
    assert facts["lidar_multibeam_overlap"]["cells"] == 2000
    assert facts["lidar_multibeam_overlap"]["median_m"] == pytest.approx(-25.0)
    assert {c["source"] for c in facts["spot_checks"]} >= {depth.LIDAR.label, depth.MULTIBEAM.label}
    assert sum(facts["cells"]["source"].values()) == facts["cells"]["sea"]


def test_written_files_match_what_the_manifest_says(built, tmp_path):
    grids, facts = built
    out = tmp_path / "seabed"
    build_seabed.write(grids, facts, out, tmp_path / "report.md")
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["schema"] == 2
    assert (manifest["grid"]["ncols"], manifest["grid"]["nrows"]) == (grid.NCOLS, grid.NROWS)
    west, south, east, north = manifest["bounds"]
    assert (
        west < grid.BOX_WEST
        and east > grid.BOX_EAST
        and south < grid.BOX_SOUTH
        and north > grid.BOX_NORTH
    )

    for name, layer in manifest["layers"].items():
        stored = publish.from_bytes((out / layer["file"]).read_bytes(), layer["dtype"])
        assert stored.shape == grid.SHAPE, name
    layer = manifest["layers"]["depth"]
    stored = publish.from_bytes((out / layer["file"]).read_bytes(), layer["dtype"])
    assert layer["offset"] + layer["scale"] * stored[50, 50] == pytest.approx(5.0)
    assert stored[50, 5] == 0

    codes = {c["code"]: c for c in manifest["layers"]["depth_source"]["classes"]}
    assert codes[depth.LIDAR.code]["cells"] == facts["cells"]["source"]["lidar"]
    assert all(c["licence"] and c["url"] for c in codes.values())
    assert manifest["quality"][codes[depth.CHART_OLD.code]["quality"]]["key"] == "old"

    drawn = manifest["drawing"]
    shape = (drawn["nrows"], drawn["ncols"])
    assert shape == drawing.SHAPE and drawn["cell_m"] == drawing.CELL_M
    assert drawn["depth"]["predictor"] == "plane"
    stored = publish.from_bytes_predicted((out / drawn["depth"]["file"]).read_bytes(), shape)
    row, col = fine(50, 50)
    assert drawn["depth"]["offset"] + drawn["depth"]["scale"] * stored[row, col] == pytest.approx(5)
    assert stored[fine(50, 5)] == 0
    for name in ("source", "bottom", "bottom_source"):
        cells = publish.from_bytes((out / drawn[name]["file"]).read_bytes(), "uint8", shape)
        assert cells.shape == shape, name
    assert drawn["source"]["past_shore"] == drawing.PAST_SHORE

    contours = json.loads((out / manifest["contours"]["file"]).read_text())
    assert {f["properties"]["depth"] for f in contours["features"]} <= set(
        manifest["contours"]["levels_m"]
    )
    report = (tmp_path / "report.md").read_text()
    assert "## LiDAR against charted soundings" in report and "## Spot checks" in report
    assert "| 1955 to 1962 | flat | 1 | -0.40 |" in report
