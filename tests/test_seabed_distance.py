"""Distance to reef and to the mainland shore, on the 100 m grid."""

import numpy as np
import pytest

from seabed import bottom, distance, grid, publish


def test_distance_to_reef_is_between_cell_centres_and_only_in_the_sea():
    sea = np.ones(grid.SHAPE, dtype=bool)
    sea[:, :10] = False
    kind = np.full(grid.SHAPE, bottom.SAND, dtype=np.uint8)
    kind[100, 100] = bottom.ROCK
    kind[50, 5] = bottom.ROCK  # rock on land is not reef
    metres = distance.to_reef(kind, sea)
    assert metres[100, 100] == 0
    assert metres[100, 103] == pytest.approx(300)
    assert metres[103, 104] == pytest.approx(500)  # three down, four across
    assert np.isnan(metres[100, 5])
    assert metres[50, 10] == pytest.approx(np.hypot(50, 90) * 100)  # the reef, not the land rock


def test_with_no_reef_there_is_no_distance_to_it():
    sea = np.ones(grid.SHAPE, dtype=bool)
    kind = np.full(grid.SHAPE, bottom.SAND, dtype=np.uint8)
    assert np.isnan(distance.to_reef(kind, sea)).all()


def test_an_island_is_not_mainland():
    sea = np.ones(grid.SHAPE, dtype=bool)
    sea[:, :20] = False  # the mainland, running off the west edge
    sea[200:210, 300:310] = False  # an island
    land = distance.mainland(sea)
    assert land[100, 5] and not land[205, 305]
    metres = distance.to_mainland(sea)
    assert metres[100, 20] == pytest.approx(100)
    assert metres[205, 311] == pytest.approx(29_200)  # past the island, measured to the mainland
    assert np.isnan(metres[205, 305]) and np.isnan(metres[100, 5])


def test_the_distances_fit_their_stored_ranges():
    far = np.full(grid.SHAPE, np.nan)
    far[0, 0:4] = [0.0, 100.0, 141.4, 30_000.0]
    reef = publish.decode(publish.encode(far, publish.REEF_DISTANCE), publish.REEF_DISTANCE)
    assert list(reef[0, 0:4]) == [0.0, 100.0, 150.0, 6350.0]  # to 25 m, and no farther than 6.35 km
    shore = publish.decode(publish.encode(far, publish.SHORE_DISTANCE), publish.SHORE_DISTANCE)
    assert list(shore[0, 0:4]) == [0.0, 100.0, 150.0, 12_700.0]
    assert np.isnan(reef[1, 1])
