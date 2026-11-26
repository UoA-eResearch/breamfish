"""The habitat build: on a made-up bay, and then the files that are committed.

The made-up bay is 30 cells square. Its west three columns are land, a reef sits in the
middle, the sea deepens eastwards, and a reserve covers the north-east corner.
"""

import json
from array import array
from pathlib import Path

import pytest

import build_habitat
from breamfish import config, grids, habitat, nztm

ROOT = Path(__file__).parent.parent
PUBLISHED = ROOT / "web" / "public" / "habitat"

N = 30
GRID = grids.Grid(west_e=1_724_100.0, north_n=6_039_600.0, cell_m=100.0, ncols=N, nrows=N)
REEF = (15, 15)
UNMAPPED = (20, 10)


def at(row, col):
    return row * N + col


def record(row, col, month, source="tagging"):
    lon, lat = nztm.unproject(*GRID.centre(at(row, col)))
    return {"source": source, "lon": f"{lon:.6f}", "lat": f"{lat:.6f}", "month": month}


@pytest.fixture(scope="module")
def scene():
    cells = [divmod(i, N) for i in range(N * N)]
    sea = [col >= 3 for _, col in cells]
    bottom = ["sand" if s else None for s in sea]
    bottom[at(*REEF)] = "rock"
    bottom[at(*UNMAPPED)] = None
    inputs = build_habitat.Inputs(
        grid=GRID,
        sea=sea,
        depth=[(col - 3) * 4.0 if s else None for (_, col), s in zip(cells, sea, strict=True)],
        bottom=bottom,
        reef=[
            100.0 * ((row - REEF[0]) ** 2 + (col - REEF[1]) ** 2) ** 0.5 if s else None
            for (row, col), s in zip(cells, sea, strict=True)
        ],
        shore=[(col - 2) * 100.0 if s else None for (_, col), s in zip(cells, sea, strict=True)],
        reserve=[row < 3 and col >= 27 for row, col in cells],
        bottom_labels={
            "rock": "Reef or rock",
            "sand": "Sand",
            "mud": "Mud",
            "soft": "Soft",
            "shell": "Shell",
            "coarse": "Gravel",
        },
        seabed_built="2026-01-01",
    )
    records = [
        record(15, 15, "11"),  # on the reef, in spring
        record(15, 6, "1"),  # in the shallows, in summer
        record(15, 29, "11", source="trawl"),  # far out and deep
        record(15, 15, ""),  # no month
        record(15, 1, "11"),  # on land, with water within a kilometre
    ]
    species = habitat.load_species("snapper")
    return species, inputs, build_habitat.build(species, inputs, records)


def values(built, name):
    return [build_habitat.unstored(code) for code in built.layers[name]]


def test_land_and_the_reserve_are_not_rated(scene):
    _, inputs, built = scene
    for name, codes in built.layers.items():
        if name == "reach.bin.gz":
            continue
        assert codes[at(10, 1)] == 0, name  # land
        assert codes[at(1, 28)] == 0, name  # reserve
    assert built.manifest["not_rated"]["reserve_cells"] == 9
    assert built.facts["rated_cells"] == sum(inputs.sea) - 9


def test_the_index_is_the_mean_of_exactly_the_factors_published_beside_it(scene):
    species, _, built = scene
    weights = {f.key: f.weight for f in species.factors}
    for season in species.seasons:
        index = values(built, f"snapper_index_{season}.bin.gz")
        parts = {
            "depth": values(built, f"snapper_depth_{season}.bin.gz"),
            "bottom": values(built, "snapper_bottom.bin.gz"),
            "reef": values(built, "snapper_reef.bin.gz"),
        }
        for cell in (at(*REEF), at(5, 8), at(25, 29), at(*UNMAPPED)):
            expected = habitat.combine({key: part[cell] for key, part in parts.items()}, weights)
            assert index[cell] == pytest.approx(expected, abs=1 / build_habitat.STEPS / 2 + 1e-9)


def test_the_reef_outranks_the_sand_beside_it_in_every_season(scene):
    species, _, built = scene
    for season in species.seasons:
        index = values(built, f"snapper_index_{season}.bin.gz")
        assert index[at(*REEF)] > index[at(REEF[0], REEF[1] + 3)] > 0
    assert values(built, "snapper_bottom.bin.gz")[at(*REEF)] == 1.0
    assert values(built, "snapper_reef.bin.gz")[at(*REEF)] == 1.0


def test_where_the_bottom_is_not_mapped_the_factor_is_left_out(scene):
    _, _, built = scene
    assert built.layers["snapper_bottom.bin.gz"][at(*UNMAPPED)] == 0
    assert built.layers["snapper_index_summer.bin.gz"][at(*UNMAPPED)] != 0
    assert built.facts["bottom_not_mapped"] == 1


def test_classes_are_cut_season_by_season_and_count_every_rated_cell(scene):
    species, _, built = scene
    classes = built.manifest["classes"]
    for season in species.seasons:
        stored = classes["breaks_stored"][season]
        assert stored == sorted(stored) and len(stored) == 4
        assert sum(classes["cells"][season]) == built.facts["rated_cells"]
        # A cell's class can be read from its stored index and the stored boundaries.
        codes = built.layers[f"snapper_index_{season}.bin.gz"]
        counted = [0] * 5
        for code in codes:
            if code:
                counted[sum(code >= b for b in stored)] += 1
        assert counted == classes["cells"][season]
    assert classes["labels"] == ["Lowest", "Low", "Middle", "High", "Highest"]


def test_reach_is_measured_from_the_mainland_shore(scene):
    _, _, built = scene
    reach = built.layers["reach.bin.gz"]
    bit = build_habitat.REACH_BIT
    assert reach[at(10, 1)] == 0  # land
    assert reach[at(10, 3)] == bit["boat"] | bit["kayak"] | bit["shore"]  # 100 m off
    assert reach[at(10, 5)] == bit["boat"] | bit["kayak"]  # 300 m: past a cast
    assert reach[at(10, 29)] == bit["boat"] | bit["kayak"]  # 2.7 km: within a paddle
    assert built.manifest["reach"]["within_m_of_mainland_shore"] == config.REACH_M
    assert built.manifest["reach"]["cells"]["shore"] == N  # one column of cells


def test_the_shore_is_a_line_of_points_each_with_a_class_for_every_season(scene):
    species, _, built = scene
    features = built.shore["features"]
    assert len(features) == N
    west = min(f["geometry"]["coordinates"][0] for f in features)
    east = max(f["geometry"]["coordinates"][0] for f in features)
    assert east - west < 0.001  # one column of cells, running north to south
    lon, lat = features[0]["geometry"]["coordinates"]
    assert nztm.project(lon, lat) == pytest.approx(GRID.centre(at(0, 3)), abs=1)
    for feature in features:
        assert set(feature["properties"]) == set(species.seasons)
        assert all(1 <= c <= 5 for c in feature["properties"].values())


def test_records_are_ranked_against_the_bay_in_their_own_season(scene):
    _, _, built = scene
    validation = built.manifest["validation"]
    assert validation["records"] == 5
    assert validation["unused"] == {"no_month": 1, "outside_or_no_water": 0}
    groups = {(g["source"], g["season"]): g for g in validation["groups"]}
    assert groups[("tagging", "spring")]["places"] == 2
    assert groups[("tagging", "summer")]["places"] == 1
    assert groups[("trawl", "spring")]["places"] == 1
    assert groups[("all", None)]["places"] == 4
    # The shallows outrank most of the bay in summer; the deep east in spring does not.
    assert groups[("tagging", "summer")]["auc"] > 0.6
    assert groups[("trawl", "spring")]["auc"] < 0.4
    assert "auc_low" not in groups[("all", None)]  # too few places for an interval


def test_written_files_are_the_ones_the_manifest_names(scene, tmp_path):
    species, _, built = scene
    out = tmp_path / "habitat"
    out.mkdir()
    (out / "left_over.bin.gz").write_bytes(b"")
    build_habitat.write(species, built, out, tmp_path / "report.md")
    manifest = json.loads((out / "manifest.json").read_text())
    named = set(manifest["index"]["files"].values()) | {manifest["reach"]["file"]}
    for factor in manifest["factors"]:
        files = factor["files"]
        named |= {files} if isinstance(files, str) else set(files.values())
    assert {p.name for p in out.glob("*.bin.gz")} == named  # and the stale file is gone
    for name in named:
        assert len(grids.read_stored(out / name, "uint8", GRID.cells)) == GRID.cells
    assert (out / manifest["reach"]["shore_points"]).exists()
    assert manifest["score"]["offset"] + manifest["score"]["scale"] * 201 == pytest.approx(1.0)
    cited = {item["ref"] for factor in manifest["factors"] for item in factor["evidence"]}
    assert cited == set(manifest["references"])
    report = (tmp_path / "report.md").read_text()
    assert "## Against the places snapper were recorded" in report
    assert "| Summer |" in report


# --- The pieces -------------------------------------------------------------------------


def test_a_point_is_inside_a_polygon_but_not_in_its_hole():
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    hole = [(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0)]
    assert build_habitat.inside([square, hole], 2, 2)
    assert not build_habitat.inside([square, hole], 5, 5)
    assert not build_habitat.inside([square, hole], 12, 5)


def test_a_reserve_given_in_degrees_marks_the_cells_whose_centres_it_holds():
    corners = [GRID.centre(at(r, c)) for r, c in ((5, 5), (5, 8), (8, 8), (8, 5))]
    ring = [list(nztm.unproject(e, n)) for e, n in corners]
    collection = {"features": [{"geometry": {"type": "Polygon", "coordinates": [ring + ring[:1]]}}]}
    marked = build_habitat.cells_inside(GRID, build_habitat.polygons_nztm(collection))
    # Centres on the outline may fall either side; the nine cells strictly inside do not.
    assert all(marked[at(r, c)] for r in (6, 7) for c in (6, 7))
    assert not marked[at(4, 6)] and not marked[at(6, 9)] and not marked[at(20, 20)]
    assert sum(marked) <= 16


def test_the_window_mean_skips_cells_that_are_not_rated():
    grid = grids.Grid(0.0, 0.0, 100.0, 4, 3)
    cells = [1.0, None, 3.0, None, None, None, None, None, 5.0, None, None, 7.0]
    out = build_habitat.window_mean(cells, grid, 1)
    assert out[0] == pytest.approx(1.0)  # itself only
    assert out[1] == pytest.approx(2.0)  # 1 and 3
    assert out[5] == pytest.approx(3.0)  # 1, 3 and 5
    assert out[7] == pytest.approx(5.0)  # 3 and 7
    assert build_habitat.window_mean([None] * 12, grid, 1) == [None] * 12


def test_stored_values_keep_two_hundred_steps_and_zero_for_nothing():
    assert build_habitat.stored(None) == 0
    assert build_habitat.stored(0.0) == 1 and build_habitat.stored(1.0) == 201
    assert build_habitat.unstored(build_habitat.stored(0.615)) == pytest.approx(0.615)
    assert build_habitat.stored(1.7) == 201 and build_habitat.stored(-0.2) == 1
    assert build_habitat.stored_break(float("inf")) == build_habitat.NEVER > 201


# --- What is committed --------------------------------------------------------------------


def test_the_committed_habitat_files_are_what_the_code_builds_today():
    """Change a curve, the formula, the seabed grids or the records, and this fails until
    scripts/build_habitat.py has been run again and its output committed."""
    species = habitat.load_species("snapper")
    inputs = build_habitat.load_inputs(
        ROOT / "web" / "public" / "seabed", ROOT / "web" / "public" / "layers" / "reserves.geojson"
    )
    records = build_habitat.load_records(habitat.SPECIES_DIR / "snapper_records.csv")
    built = build_habitat.build(species, inputs, records)

    for name, codes in built.layers.items():
        committed = grids.read_stored(PUBLISHED / name, "uint8", inputs.grid.cells)
        assert committed == array("B", codes), f"{name} is out of date"
    assert {p.name for p in PUBLISHED.glob("*.bin.gz")} == set(built.layers)

    committed = json.loads((PUBLISHED / "manifest.json").read_text())
    fresh = json.loads(json.dumps(built.manifest))
    committed.pop("built"), fresh.pop("built")
    assert committed == fresh, "manifest.json is out of date"
    assert json.loads((PUBLISHED / "shore.geojson").read_text()) == built.shore
