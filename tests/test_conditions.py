import pytest

from breamfish import config
from breamfish.conditions import in_sector, rate

ZONES = {zone["id"]: zone for zone in config.ZONES}
ENTRANCE, INNER, OUTER = ZONES["entrance"], ZONES["inner"], ZONES["outer"]

# Written out again here, not read from config, so a slip in config.py is caught.
# style: {variable: (good limit, fair limit, name used in "limit")}
LIMITS = {
    "boat": {
        "wind_kn": (10, 15, "wind"),
        "gust_kn": (15, 22, "gust"),
        "wave_m": (1.0, 1.5, "swell"),
    },
    "kayak": {
        "wind_kn": (8, 12, "wind"),
        "gust_kn": (12, 17, "gust"),
        "wave_m": (0.5, 0.8, "swell"),
    },
    "shore": {
        "wind_kn": (12, 18, "wind"),
        "gust_kn": (18, 25, "gust"),
        "wave_m": (1.2, 2.0, "swell"),
    },
}
STEP = {"wind_kn": 0.1, "gust_kn": 0.1, "wave_m": 0.01}  # one unit of published precision


def hour(**values):
    """A flat calm, dry hour at slack water, with anything given overriding it."""
    calm = {"wind_kn": 0, "gust_kn": 0, "wave_m": 0, "rain_mm": 0, "wind_dir": 0, "tide_rate": 0}
    return calm | values


# --- sectors ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("direction", "sector", "expected"),
    [
        (60, (60, 160), True),  # both ends are included
        (160, (60, 160), True),
        (100, (60, 160), True),
        (59, (60, 160), False),
        (161, (60, 160), False),
        (300, (300, 60), True),  # a sector that wraps through north
        (350, (300, 60), True),
        (0, (300, 60), True),
        (360, (300, 60), True),
        (60, (300, 60), True),
        (61, (300, 60), False),
        (180, (300, 60), False),
        (299, (300, 60), False),
        (90, None, False),  # the outer zone has no sectors
        (None, (60, 160), False),  # no wind direction for the hour
    ],
)
def test_in_sector(direction, sector, expected):
    assert in_sector(direction, sector) is expected


# --- thresholds ---------------------------------------------------------------------


@pytest.mark.parametrize("style", LIMITS)
@pytest.mark.parametrize("variable", ["wind_kn", "gust_kn", "wave_m"])
def test_every_threshold_boundary(style, variable):
    good, fair, name = LIMITS[style][variable]
    step = STEP[variable]

    assert rate(style, OUTER, hour(**{variable: good})) == (3, "ok")
    assert rate(style, OUTER, hour(**{variable: good + step})) == (2, name)
    assert rate(style, OUTER, hour(**{variable: fair})) == (2, name)
    assert rate(style, OUTER, hour(**{variable: fair + step})) == (1, name)


def test_config_holds_the_agreed_threshold_table():
    for style, variables in LIMITS.items():
        for variable, (good, fair, _) in variables.items():
            assert config.THRESHOLDS[style]["good"][variable] == good
            assert config.THRESHOLDS[style]["fair"][variable] == fair


def test_class_is_the_worst_of_the_three():
    assert rate("boat", OUTER, hour(wind_kn=5, gust_kn=30, wave_m=0.2)) == (1, "gust")
    assert rate("boat", OUTER, hour(wind_kn=12, gust_kn=14, wave_m=2.0)) == (1, "swell")


def test_ties_are_named_gust_then_wind_then_swell():
    assert rate("boat", OUTER, hour(wind_kn=12, gust_kn=20, wave_m=1.2)) == (2, "gust")
    assert rate("boat", OUTER, hour(wind_kn=12, gust_kn=10, wave_m=1.2)) == (2, "wind")
    assert rate("boat", OUTER, hour(wind_kn=5, gust_kn=10, wave_m=1.2)) == (2, "swell")


# --- missing data -------------------------------------------------------------------


def test_no_wind_or_no_gust_is_no_data():
    assert rate("boat", OUTER, hour(wind_kn=None)) == (0, "no_data")
    assert rate("boat", OUTER, hour(gust_kn=None)) == (0, "no_data")
    # Modifiers do not turn "no data" into a rating.
    assert rate("boat", OUTER, hour(wind_kn=None, rain_mm=10)) == (0, "no_data")


def test_missing_wave_is_rated_on_wind_and_gust():
    assert rate("boat", OUTER, hour(wave_m=None)) == (3, "ok")
    assert rate("boat", OUTER, hour(wave_m=None, wind_kn=12)) == (2, "wind")


def test_missing_rain_direction_or_tide_rate_skips_those_modifiers():
    quiet = hour(wind_kn=5, rain_mm=None, wind_dir=None, tide_rate=None)
    assert rate("kayak", ENTRANCE, quiet) == (3, "ok")


# --- modifiers ----------------------------------------------------------------------


@pytest.mark.parametrize("style", ["boat", "kayak", "shore"])
def test_rain_lowers_any_style(style):
    assert rate(style, OUTER, hour(rain_mm=4.0)) == (2, "rain")
    assert rate(style, OUTER, hour(rain_mm=3.9)) == (3, "ok")


def test_offshore_wind_lowers_kayak_only():
    northerly = hour(wind_kn=8, gust_kn=10, wind_dir=350)  # entrance: offshore is 300..60
    assert rate("kayak", ENTRANCE, northerly) == (2, "offshore_wind")
    assert rate("boat", ENTRANCE, northerly) == (3, "ok")
    assert rate("shore", ENTRANCE, northerly) == (3, "ok")
    # Not below 8 kn, not from outside the sector, not where there is no sector.
    assert rate("kayak", ENTRANCE, northerly | {"wind_kn": 7.9}) == (3, "ok")
    assert rate("kayak", ENTRANCE, northerly | {"wind_dir": 200}) == (3, "ok")
    assert rate("kayak", OUTER, northerly) == (3, "ok")


def test_onshore_wind_lowers_shore_only():
    easterly = hour(wind_kn=15, gust_kn=18, wind_dir=90)  # inner: onshore is 20..140
    assert rate("shore", INNER, easterly) == (1, "onshore_wind")  # fair on wind, then lowered
    assert rate("boat", INNER, easterly) == (2, "gust")
    assert rate("shore", INNER, easterly | {"wind_kn": 14.9}) == (2, "wind")
    assert rate("shore", INNER, easterly | {"wind_dir": 250}) == (2, "wind")
    assert rate("shore", OUTER, easterly) == (2, "wind")


def test_wind_against_tide_at_the_entrance():
    # Tide falling at 0.25 m/h against a 12 kn onshore wind (entrance: 60..160).
    ebb = hour(wind_kn=12, gust_kn=14, wind_dir=100, tide_rate=-0.25)
    assert rate("boat", ENTRANCE, ebb) == (1, "wind_against_tide")  # fair on wind, then lowered
    assert rate("kayak", ENTRANCE, ebb) == (1, "wind_against_tide")
    assert rate("shore", ENTRANCE, ebb) == (3, "ok")  # shore is not affected

    assert rate("boat", ENTRANCE, ebb | {"tide_rate": -0.24}) == (2, "wind")  # not ebbing hard
    assert rate("boat", ENTRANCE, ebb | {"tide_rate": 0.4}) == (2, "wind")  # flooding
    assert rate("boat", ENTRANCE, ebb | {"wind_dir": 200}) == (2, "wind")  # not onshore
    assert rate("boat", INNER, ebb) == (2, "wind")  # onshore there too, but no ebb hazard


def test_wind_against_tide_needs_wind_or_waves():
    ebb = hour(wind_kn=5, gust_kn=8, wind_dir=100, tide_rate=-0.4)
    assert rate("boat", ENTRANCE, ebb) == (3, "ok")  # light wind, flat sea
    assert rate("boat", ENTRANCE, ebb | {"wave_m": 1.0}) == (2, "wind_against_tide")
    assert rate("boat", ENTRANCE, ebb | {"wave_m": 0.99}) == (3, "ok")
    assert rate("boat", ENTRANCE, ebb | {"wave_m": None, "wind_kn": 12}) == (1, "wind_against_tide")


def test_modifiers_stack_and_the_last_one_is_named():
    both = hour(wind_kn=5, gust_kn=8, wave_m=1.0, wind_dir=100, tide_rate=-0.4, rain_mm=5)
    assert rate("boat", ENTRANCE, both) == (1, "wind_against_tide")  # 3, less rain, less ebb


def test_modifiers_never_go_below_poor():
    gale = hour(wind_kn=30, gust_kn=45, wave_m=3.0, wind_dir=100, tide_rate=-0.4, rain_mm=9)
    assert rate("boat", ENTRANCE, gale) == (1, "wind_against_tide")
    assert rate("shore", ENTRANCE, gale) == (1, "onshore_wind")
    assert rate("shore", OUTER, gale) == (1, "rain")
