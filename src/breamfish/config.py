"""Everything tunable in one place: zones, thresholds, source URLs, cache ages."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from breamfish import __version__

TIMEZONE = "Pacific/Auckland"
NZ = ZoneInfo(TIMEZONE)

# conditions.json covers eight local days: today from midnight (New Zealand time), so
# the site can show the whole of today, and the seven days after it. One entry per hour.
HOURS = 192

# --- HTTP ---------------------------------------------------------------------------

USER_AGENT = f"breamfish/{__version__} (+https://github.com/UoA-eResearch/breamfish)"
HTTP_TIMEOUT_S = 30
HTTP_BACKOFF_S = (2, 6)  # seconds to wait before each retry, so two retries

# --- Sources (all keyless) ----------------------------------------------------------

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
# Open-Meteo series start at 00:00 UTC. Local midnight is 11:00 or 12:00 UTC on the day
# before, so one past day is needed, and nine days ahead cover the end of the window
# whatever the hour of the run.
PAST_DAYS = 1
FORECAST_DAYS = 9

# cell_selection, checked on 2026-11-26 by comparing the coordinates Open-Meteo returned
# and looking up their elevation (0 m = water):
#   forecast, default (land):  entrance -> -35.817, 174.542  on Whangarei Heads, 2 m
#                              inner    -> -35.888, 174.419  9 km away, inland of Ruakaka, 11 m
#                              outer    -> -35.958, 174.644  open water
#   forecast, "sea":           entrance -> -35.888, 174.535  open water 5 km south of the entrance
#                              inner    -> -35.958, 174.528  open water 4 km from the point
#                              outer    -> -35.958, 174.644  unchanged
#   marine, "sea":             entrance -> -35.875, 174.625  7 km east of the point, off Bream Head
#                              inner    -> -35.958, 174.625  7 km east of the point
#                              outer    -> -35.958, 174.708  cell centred on Taranga (Hen) Island
# So "sea" puts all three weather points over water in three different cells. The wave
# model has no cell closer inshore than 174.625 E, so entrance and inner wave figures are
# for the open bay and will overstate the sheltered water close to the beach.
CELL_SELECTION = "sea"

# The wind drawn on the map: one more forecast request, for a lattice of points laid out
# row by row from the north-west corner. Checked on 2026-11-27: these 48 points came
# back as 48 different model cells, 0.0703 degrees of latitude apart (7.8 km) and about
# 0.116 of longitude (10.5 km), each row starting a little further west than the one
# above it. So the bay is four or five cells across, and that is all the detail there is.
# "nearest" and not "sea": this is the model's own field, land cells included.
# One request costs 48 of Open-Meteo's calls: about 1,150 a day at one run an hour.
WIND_LATTICE = {
    "north": -35.70,
    "west": 174.30,
    "dlat": 0.07,
    "dlon": 0.115,
    "nrows": 8,
    "ncols": 6,
}
WIND_CELL_SELECTION = "nearest"
# Same shape as WEATHER_FIELDS; the key and the decimal places are not used.
WIND_FIELD_FIELDS = [
    ("speed", "wind_speed_10m", 1),
    ("direction", "wind_direction_10m", 0),
]

# One file per calendar year. Times in it are New Zealand local time.
TIDE_URL = (
    "https://static.charts.linz.govt.nz/tide-tables/maj-ports/csv/Marsden%20Point%20{year}.csv"
)
TIDE_PORT = "Marsden Point"
TIDE_DATUM = "chart datum"

# A cached copy older than this is not used when a fetch fails.
OPENMETEO_MAX_AGE = timedelta(hours=12)
TIDE_MAX_AGE = timedelta(days=60)
# A year of tide predictions does not change, so do not ask for it again within a week.
TIDE_REFETCH_AFTER = timedelta(days=7)

# Each entry: (key in conditions.json, Open-Meteo variable, decimal places).
WEATHER_FIELDS = [
    ("wind_kn", "wind_speed_10m", 1),
    ("gust_kn", "wind_gusts_10m", 1),
    ("wind_dir", "wind_direction_10m", 0),
    ("rain_mm", "precipitation", 1),
    ("cloud_pct", "cloud_cover", 0),
    ("air_c", "temperature_2m", 1),
]
MARINE_FIELDS = [
    ("wave_m", "wave_height", 2),
    ("wave_dir", "wave_direction", 0),
    ("wave_period_s", "wave_period", 1),
    ("swell_m", "swell_wave_height", 2),
    ("swell_period_s", "swell_wave_period", 1),
    ("sst_c", "sea_surface_temperature", 1),
]

# --- Places -------------------------------------------------------------------------

# Sunrise and sunset are worked out for one point in the middle of the bay.
SUN_LAT, SUN_LON = -35.90, 174.55

# lat/lon is the map marker; weather and marine are the points asked of Open-Meteo.
# A sector (a, b) is the range of directions the wind blows FROM, in degrees, clockwise
# from a to b. It may wrap through north, as 300..60 does. None means no such sector.
ZONES = [
    {
        "id": "entrance",
        "name": "Harbour entrance and Urquharts Bay",
        "lat": -35.845,
        "lon": 174.53,
        "weather": (-35.845, 174.53),
        "marine": (-35.88, 174.55),
        "offshore_from": (300, 60),
        "onshore_from": (60, 160),
        "ebb_hazard": True,
    },
    {
        "id": "inner",
        "name": "Inner bay: Ruakaka to Waipu",
        "lat": -35.93,
        "lon": 174.50,
        "weather": (-35.93, 174.50),
        "marine": (-35.96, 174.55),
        "offshore_from": (190, 330),
        "onshore_from": (20, 140),
        "ebb_hazard": False,
    },
    {
        "id": "outer",
        "name": "Outer bay and Hen and Chickens",
        "lat": -35.93,
        "lon": 174.70,
        "weather": (-35.93, 174.70),
        "marine": (-35.93, 174.70),
        "offshore_from": None,
        "onshore_from": None,
        "ebb_hazard": False,
    },
]

# --- Comfort rating -----------------------------------------------------------------

STYLES = ("boat", "kayak", "shore")

# Upper limits. At or under every "good" limit is good (3), at or under every "fair"
# limit is fair (2), anything more is poor (1).
THRESHOLDS = {
    "boat": {
        "good": {"wind_kn": 10, "gust_kn": 15, "wave_m": 1.0},
        "fair": {"wind_kn": 15, "gust_kn": 22, "wave_m": 1.5},
    },
    "kayak": {
        "good": {"wind_kn": 8, "gust_kn": 12, "wave_m": 0.5},
        "fair": {"wind_kn": 12, "gust_kn": 17, "wave_m": 0.8},
    },
    "shore": {
        "good": {"wind_kn": 12, "gust_kn": 18, "wave_m": 1.2},
        "fair": {"wind_kn": 18, "gust_kn": 25, "wave_m": 2.0},
    },
}

# Each of these knocks the rating down one class. See conditions.rate for the rules.
MODIFIERS = {
    "rain_mm": 4.0,  # any style: this much rain or more in the hour
    "offshore_wind_kn": 8,  # kayak: wind blowing off the land at this speed or more
    "onshore_wind_kn": 15,  # shore: wind blowing onto the beach at this speed or more
    "ebb_rate_m_per_h": -0.25,  # boat and kayak: tide falling this fast or faster...
    "ebb_wind_kn": 12,  # ...against an onshore wind of this speed or more...
    "ebb_wave_m": 1.0,  # ...or against waves this high or higher
}

# --- Habitat index ------------------------------------------------------------------

# How far from the mainland shore each style of fishing is taken to reach, in metres;
# None is everywhere. Beyond it the habitat map is greyed out for that style. These are
# round figures chosen here, not rules and not safety limits:
#   kayak  3 km is about half an hour's paddle each way for a fishing kayak;
#   shore  150 m takes in the water a cast can reach: the 100 m cells that touch the
#          land, corner to corner.
# Islands do not count as shore: landing on the Hen and Chickens is not allowed.
REACH_M = {"boat": None, "kayak": 3000, "shore": 150}

# When the index is checked against a place snapper were recorded, the place is taken
# as everything within this distance east-west and north-south of the stated position.
# The largest group of records (the 1993 tagging stations) is given to the nearest
# minute of arc, about 1.5 by 1.9 km, and a trawl tow is a kilometre or more long.
RECORD_WINDOW_M = 1000
