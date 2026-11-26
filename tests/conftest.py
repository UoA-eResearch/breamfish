"""Shared fixtures. Nothing here or in any test touches the network.

The files under tests/fixtures are cut down from real responses:
- marsden_point_2026_sample.csv: the three heading lines and a few rows of the LINZ
  tide predictions for Marsden Point (Land Information New Zealand, CC BY 4.0), with
  the byte order mark and CRLF line endings of the original.
- openmeteo_forecast.json, openmeteo_marine.json: the first 12 hours of the three-point
  Open-Meteo responses of 2026-11-26 (starting 00:00 UTC).
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# The run time used throughout: four hours into the fixture forecasts, which is
# 17:05 on 26 November in New Zealand (daylight time, UTC+13).
NOW = datetime(2026, 11, 26, 4, 5, 12, tzinfo=UTC)

# The published window starts at local midnight, 11:00 UTC on the 25th. So the canned
# forecasts (00:00 to 11:00 UTC on the 26th) fill entries 13 to 24, and the hour of the
# run is entry 17.
FIRST_CANNED = 13
AT_NOW = 17


@pytest.fixture
def tide_csv() -> bytes:
    return (FIXTURES / "marsden_point_2026_sample.csv").read_bytes()


@pytest.fixture
def forecast_json() -> bytes:
    return (FIXTURES / "openmeteo_forecast.json").read_bytes()


@pytest.fixture
def marine_json() -> bytes:
    return (FIXTURES / "openmeteo_marine.json").read_bytes()


def fake_get(responses: dict, calls: list | None = None):
    """Stand-in for the HTTP layer: get(url, params) -> bytes.

    responses maps a piece of URL to the body to return, or to an exception to raise.
    Every URL asked for is appended to calls.
    """

    def get(url, params=None):
        if calls is not None:
            calls.append(url)
        for fragment, response in responses.items():
            if fragment in url:
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError(f"test asked for an unexpected URL: {url}")

    return get
