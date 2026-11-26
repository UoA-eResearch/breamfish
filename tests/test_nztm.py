"""The NZTM arithmetic, against PROJ.

The seabed manifest carries five points of the grid that PROJ projected when the grids
were built; the browser checks its own arithmetic against the same five.
"""

import json
from pathlib import Path

import pytest

from breamfish import nztm

MANIFEST = Path(__file__).parent.parent / "web" / "public" / "seabed" / "manifest.json"
POINTS = json.loads(MANIFEST.read_text())["projection_check"]


@pytest.mark.parametrize("lon, lat, easting, northing", POINTS)
def test_projection_agrees_with_proj(lon, lat, easting, northing):
    e, n = nztm.project(lon, lat)
    # The manifest keeps seven decimal places of a degree, which is about a centimetre.
    assert e == pytest.approx(easting, abs=0.02)
    assert n == pytest.approx(northing, abs=0.02)


@pytest.mark.parametrize("lon, lat, easting, northing", POINTS)
def test_unprojection_is_the_inverse(lon, lat, easting, northing):
    back_lon, back_lat = nztm.unproject(easting, northing)
    assert back_lon == pytest.approx(lon, abs=2e-7)
    assert back_lat == pytest.approx(lat, abs=2e-7)
    assert nztm.project(back_lon, back_lat) == pytest.approx((easting, northing), abs=1e-4)


def test_the_central_meridian_is_a_straight_line_north():
    easting, _ = nztm.project(173.0, -36.0)
    assert easting == pytest.approx(1_600_000.0, abs=1e-6)
