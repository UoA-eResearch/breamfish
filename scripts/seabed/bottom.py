"""Bottom type: what the seabed is made of, and which source said so.

Three sources, most specific first:

1. LINZ chart rock: seabed-area polygons charted as rock, and charted underwater rocks.
2. LINZ chart seabed samples: a surveyor's note of the bottom at one point. It speaks
   for the cell it is in and no further.
3. The DOC Northland habitat map (Kerr 2010): polygons for the whole coast, at a coarse
   mapping scale. For most of open Bream Bay it says only "soft sediments", without
   telling sand from mud, and that is published as its own class instead of a guess.
"""

from __future__ import annotations

import numpy as np

from seabed import grid

# The byte stored in the bottom grid.
UNKNOWN, ROCK, SAND, MUD, SHELL, COARSE, SOFT = 0, 1, 2, 3, 4, 5, 6

CLASSES = (
    {"code": UNKNOWN, "key": "unknown", "label": "Not mapped"},
    {"code": ROCK, "key": "rock", "label": "Reef or rock"},
    {"code": SAND, "key": "sand", "label": "Sand"},
    {"code": MUD, "key": "mud", "label": "Mud or fine sediment"},
    {"code": SHELL, "key": "shell", "label": "Shell"},
    {"code": COARSE, "key": "coarse", "label": "Gravel or coarse sediment"},
    {"code": SOFT, "key": "soft", "label": "Soft sediment, sand or mud not told apart"},
)

# The byte stored in the bottom_source grid.
NO_SOURCE, CHART_ROCK, CHART_SAMPLE, HABITAT_MAP = 0, 1, 2, 3

SOURCES = (
    {"code": NO_SOURCE, "key": "none", "label": "No information"},
    {"code": CHART_ROCK, "key": "chart_rock", "label": "LINZ chart, charted rock"},
    {"code": CHART_SAMPLE, "key": "chart_sample", "label": "LINZ chart, seabed sample here"},
    {"code": HABITAT_MAP, "key": "habitat_map", "label": "DOC habitat map (2010), coarse scale"},
)

# S-57 "nature of surface" codes (attribute NATSUR), as used on LINZ charts.
_NATSUR = {
    1: MUD,  # mud
    2: MUD,  # clay
    3: MUD,  # silt
    4: SAND,  # sand
    5: COARSE,  # stone
    6: COARSE,  # gravel
    7: COARSE,  # pebbles
    8: COARSE,  # cobbles
    9: ROCK,  # rock
    11: ROCK,  # lava
    14: ROCK,  # coral
    17: SHELL,  # shells
    18: ROCK,  # boulder
}

# The Substrate attribute of the DOC habitat map.
_SUBSTRATE = {
    "rock": ROCK,
    "sand": SAND,
    "mud": MUD,
    "fine sediments": MUD,
    "gravel": COARSE,
    "coarse sediments": COARSE,
    "soft sediments": SOFT,
}


def class_of_natsur(natsur) -> int:
    """Bottom class of a chart NATSUR value such as "4", "4,17" or 9.

    A chart lists the main constituent first ("4,17" is sand with shells), so the first
    code decides. Anything unrecognised is UNKNOWN.
    """
    if natsur is None:
        return UNKNOWN
    first = str(natsur).replace(";", ",").split(",")[0].strip()
    try:
        return _NATSUR.get(int(float(first)), UNKNOWN)
    except ValueError:
        return UNKNOWN


def class_of_substrate(substrate) -> int:
    """Bottom class of a DOC habitat map Substrate value. Blank (islands) is UNKNOWN."""
    return _SUBSTRATE.get(str(substrate or "").strip().lower(), UNKNOWN)


def merge(layers) -> tuple[np.ndarray, np.ndarray]:
    """Combine bottom-class grids, most specific source first.

    layers is a list of (source code, class grid) where UNKNOWN means the source says
    nothing about a cell. Returns the class grid and the source of each cell's class.
    """
    bottom = np.full(grid.SHAPE, UNKNOWN, dtype=np.uint8)
    source = np.full(grid.SHAPE, NO_SOURCE, dtype=np.uint8)
    for code, classes in layers:
        take = (bottom == UNKNOWN) & (classes != UNKNOWN)
        bottom[take] = classes[take]
        source[take] = code
    return bottom, source


def points_to_cells(easting, northing, classes) -> np.ndarray:
    """A class grid from point observations: each point sets the one cell it falls in.

    Where two points share a cell, rock wins (it matters most to a fisher and to an
    anchor), then the first listed.
    """
    out = np.full(grid.SHAPE, UNKNOWN, dtype=np.uint8)
    rows, cols = grid.cell_of(easting, northing)
    keep = grid.inside(rows, cols) & (np.asarray(classes) != UNKNOWN)
    for row, col, cls in zip(rows[keep], cols[keep], np.asarray(classes)[keep], strict=True):
        if out[row, col] == UNKNOWN or cls == ROCK:
            out[row, col] = cls
    return out
