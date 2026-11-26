"""Longitude and latitude to New Zealand Transverse Mercator 2000 (EPSG:2193).

The seabed grids are laid out in NZTM, so a point given in degrees (a reserve boundary,
a survey station) has to be projected to find its cell. This is the series LINZ
publishes for the projection, good to a millimetre here, and the same arithmetic as
web/src/seabed.ts. tests/test_nztm.py checks it against points worked out by PROJ.
"""

from math import cos, degrees, radians, sin, sqrt

A = 6378137.0  # GRS80 semi-major axis
F = 1 / 298.257222101
K0 = 0.9996
LON0 = radians(173.0)
FALSE_E = 1_600_000.0
FALSE_N = 10_000_000.0

_E2 = 2 * F - F * F
_E4 = _E2 * _E2
_E6 = _E4 * _E2
_A0 = 1 - _E2 / 4 - 3 * _E4 / 64 - 5 * _E6 / 256
_A2 = 3 / 8 * (_E2 + _E4 / 4 + 15 * _E6 / 128)
_A4 = 15 / 256 * (_E4 + 3 * _E6 / 4)
_A6 = 35 * _E6 / 3072


def project(lon: float, lat: float) -> tuple[float, float]:
    """(easting, northing) in metres of a point given in degrees."""
    phi = radians(lat)
    s, c = sin(phi), cos(phi)
    t2 = (s / c) ** 2
    t4, t6 = t2 * t2, t2 * t2 * t2
    m = A * (_A0 * phi - _A2 * sin(2 * phi) + _A4 * sin(4 * phi) - _A6 * sin(6 * phi))
    w_ = 1 - _E2 * s * s
    nu = A / sqrt(w_)
    psi = w_ / (1 - _E2)  # nu / rho
    psi2, psi3, psi4 = psi * psi, psi**3, psi**4
    w = radians(lon) - LON0
    x = w * w * c * c

    e1 = x / 6 * (psi - t2)
    e2 = x * x / 120 * (4 * psi3 * (1 - 6 * t2) + psi2 * (1 + 8 * t2) - psi * 2 * t2 + t4)
    e3 = x**3 / 5040 * (61 - 479 * t2 + 179 * t4 - t6)
    n1 = x / 12 * (4 * psi2 + psi - t2)
    n2 = (
        x
        * x
        / 360
        * (
            8 * psi4 * (11 - 24 * t2)
            - 28 * psi3 * (1 - 6 * t2)
            + psi2 * (1 - 32 * t2)
            - psi * 2 * t2
            + t4
        )
    )
    n3 = x**3 / 20160 * (1385 - 3111 * t2 + 543 * t4 - t6)

    easting = FALSE_E + K0 * nu * w * c * (1 + e1 + e2 + e3)
    northing = FALSE_N + K0 * (m + nu * s * w * w / 2 * c * (1 + n1 + n2 + n3))
    return easting, northing


def unproject(easting: float, northing: float) -> tuple[float, float]:
    """(longitude, latitude) in degrees of a point given in NZTM metres.

    Found by correcting a guess until it projects back onto the point; each round cuts
    the error by a factor of a few hundred, and six leave it far under a millimetre.
    """
    lon, lat = 173.0 + (easting - FALSE_E) / 90_000, (northing - FALSE_N) / 111_000
    for _ in range(6):
        e, n = project(lon, lat)
        lat += degrees((northing - n) / (K0 * A))
        lon += degrees((easting - e) / (K0 * A * cos(radians(lat))))
    return lon, lat
