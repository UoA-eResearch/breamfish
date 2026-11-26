"""Bottom type: reading the chart and habitat-map codes, and which source wins."""

import numpy as np

from seabed import bottom, grid


def test_chart_nature_of_surface_codes():
    assert bottom.class_of_natsur("9") == bottom.ROCK
    assert bottom.class_of_natsur(4) == bottom.SAND
    assert bottom.class_of_natsur("1") == bottom.MUD
    assert bottom.class_of_natsur("17") == bottom.SHELL
    assert bottom.class_of_natsur("6") == bottom.COARSE
    # The first constituent listed is the main one: sand with shells is sand.
    assert bottom.class_of_natsur("4,17") == bottom.SAND
    assert bottom.class_of_natsur("17,4") == bottom.SHELL
    for nothing in (None, "", "99", "weed"):
        assert bottom.class_of_natsur(nothing) == bottom.UNKNOWN


def test_habitat_map_substrates():
    assert bottom.class_of_substrate("rock") == bottom.ROCK
    assert bottom.class_of_substrate("Sand") == bottom.SAND
    assert bottom.class_of_substrate("fine sediments") == bottom.MUD
    assert bottom.class_of_substrate("coarse sediments") == bottom.COARSE
    # "Soft sediments" does not say sand or mud, and is not turned into either.
    assert bottom.class_of_substrate("soft sediments") == bottom.SOFT
    assert bottom.class_of_substrate(" ") == bottom.UNKNOWN  # islands
    assert bottom.class_of_substrate(None) == bottom.UNKNOWN


def test_merge_prefers_the_more_specific_source():
    rock = np.full(grid.SHAPE, bottom.UNKNOWN, dtype=np.uint8)
    samples = rock.copy()
    habitat = np.full(grid.SHAPE, bottom.SOFT, dtype=np.uint8)
    rock[0, 0] = bottom.ROCK
    samples[0, 0] = bottom.SAND
    samples[0, 1] = bottom.SHELL
    habitat[0, 3] = bottom.UNKNOWN
    kind, source = bottom.merge(
        [
            (bottom.CHART_ROCK, rock),
            (bottom.CHART_SAMPLE, samples),
            (bottom.HABITAT_MAP, habitat),
        ]
    )
    assert list(kind[0, 0:4]) == [bottom.ROCK, bottom.SHELL, bottom.SOFT, bottom.UNKNOWN]
    assert list(source[0, 0:4]) == [
        bottom.CHART_ROCK,
        bottom.CHART_SAMPLE,
        bottom.HABITAT_MAP,
        bottom.NO_SOURCE,
    ]


def test_a_sample_marks_only_its_own_cell_and_rock_wins_a_shared_cell():
    easting = np.array(
        [grid.WEST_E + 150.0, grid.WEST_E + 160.0, grid.WEST_E + 950.0, grid.WEST_E - 5]
    )
    northing = np.full(4, grid.NORTH_N - 50.0)
    classes = np.array([bottom.SAND, bottom.ROCK, bottom.MUD, bottom.ROCK])
    cells = bottom.points_to_cells(easting, northing, classes)
    assert cells[0, 1] == bottom.ROCK
    assert cells[0, 9] == bottom.MUD
    assert (cells != bottom.UNKNOWN).sum() == 2  # the point outside the grid is ignored


def test_every_class_and_source_has_one_code_and_a_label():
    assert [c["code"] for c in bottom.CLASSES] == list(range(len(bottom.CLASSES)))
    assert [s["code"] for s in bottom.SOURCES] == list(range(len(bottom.SOURCES)))
    assert all(c["label"] for c in bottom.CLASSES + bottom.SOURCES)
