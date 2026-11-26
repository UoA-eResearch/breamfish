"""The comfort rating: 3 good, 2 fair, 1 poor, 0 no data."""

from breamfish import config


def in_sector(direction, sector) -> bool:
    """Is a wind direction (degrees it blows FROM) inside sector (start, end)?

    A sector runs clockwise from start to end, both ends included, and may wrap
    through north: 350 is inside (300, 60).
    """
    if direction is None or sector is None:
        return False
    start, end = sector
    return (direction - start) % 360 <= (end - start) % 360


def grade(value, good_limit, fair_limit) -> int:
    if value <= good_limit:
        return 3
    if value <= fair_limit:
        return 2
    return 1


def rate(style: str, zone: dict, hour: dict) -> tuple[int, str]:
    """Rate one hour for one style in one zone. Returns (class, limit).

    hour holds wind_kn, gust_kn, wave_m, rain_mm, wind_dir and tide_rate, any of which
    may be None. limit names what held the class down, or "ok".
    """
    wind, gust, wave = hour["wind_kn"], hour["gust_kn"], hour["wave_m"]
    if wind is None or gust is None:
        return 0, "no_data"

    good = config.THRESHOLDS[style]["good"]
    fair = config.THRESHOLDS[style]["fair"]
    # Listed in tie-break order: when two are equally bad, the first one is named.
    grades = [
        ("gust", grade(gust, good["gust_kn"], fair["gust_kn"])),
        ("wind", grade(wind, good["wind_kn"], fair["wind_kn"])),
    ]
    if wave is not None:  # no wave data: rate on wind and gust alone
        grades.append(("swell", grade(wave, good["wave_m"], fair["wave_m"])))
    limit, level = min(grades, key=lambda item: item[1])
    if level == 3:
        limit = "ok"

    mod = config.MODIFIERS
    rain, tide_rate = hour["rain_mm"], hour["tide_rate"]
    offshore = in_sector(hour["wind_dir"], zone["offshore_from"])
    onshore = in_sector(hour["wind_dir"], zone["onshore_from"])
    ebbing = tide_rate is not None and tide_rate <= mod["ebb_rate_m_per_h"]
    rough = wind >= mod["ebb_wind_kn"] or (wave is not None and wave >= mod["ebb_wave_m"])

    # Each modifier that applies lowers the class by one (never below 1) and takes over
    # as the limit. They are applied in this order, so the last one to apply is named.
    modifiers = [
        ("rain", rain is not None and rain >= mod["rain_mm"]),
        ("offshore_wind", style == "kayak" and offshore and wind >= mod["offshore_wind_kn"]),
        ("onshore_wind", style == "shore" and onshore and wind >= mod["onshore_wind_kn"]),
        (
            "wind_against_tide",
            style in ("boat", "kayak") and zone["ebb_hazard"] and ebbing and onshore and rough,
        ),
    ]
    for name, applies in modifiers:
        if applies:
            level = max(level - 1, 1)
            limit = name
    return level, limit
