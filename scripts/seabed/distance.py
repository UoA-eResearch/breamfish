"""Distances the habitat index and the reach of each fishing style are worked out from.

Both are measured between cell centres on the 100 m grid, so they come in steps of a
cell and a reef or a shore narrower than a cell is placed to the nearest 100 m.
"""

from __future__ import annotations

import numpy as np

from seabed import bottom, grid


def to_nearest(target: np.ndarray, sea: np.ndarray) -> np.ndarray:
    """Metres from each sea cell to the nearest cell where target is true (0 on one).

    NaN on land, and everywhere if there is no such cell.
    """
    from scipy.ndimage import distance_transform_edt

    if not target.any():
        return np.full(grid.SHAPE, np.nan)
    metres = distance_transform_edt(~target) * grid.CELL_M
    return np.where(sea, metres, np.nan)


def to_reef(kind: np.ndarray, sea: np.ndarray) -> np.ndarray:
    """Metres from each sea cell to the nearest cell of reef or rock."""
    return to_nearest((kind == bottom.ROCK) & sea, sea)


def mainland(sea: np.ndarray) -> np.ndarray:
    """The land that is mainland: every piece of land that reaches the edge of the grid.

    Islands lie wholly inside the grid here (the Hen and Chickens, Sail Rock, the islets
    of the harbour); the mainland, and the Whangārei Heads peninsula that joins it north
    of the grid, run off its edge.
    """
    from scipy.ndimage import label

    pieces, _ = label(~sea, structure=np.ones((3, 3), dtype=bool))
    edge = np.concatenate([pieces[0], pieces[-1], pieces[:, 0], pieces[:, -1]])
    reaching = np.unique(edge[edge != 0])
    return np.isin(pieces, reaching)


def to_mainland(sea: np.ndarray) -> np.ndarray:
    """Metres from each sea cell to the nearest mainland cell."""
    return to_nearest(mainland(sea), sea)
