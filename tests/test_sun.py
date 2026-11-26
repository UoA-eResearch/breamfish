from datetime import UTC, datetime, timedelta

from breamfish import config
from breamfish.sun import sun_times

CLOSE = timedelta(minutes=3)


def utc(*args):
    return datetime(*args, tzinfo=UTC)


def test_one_entry_for_each_local_date_the_window_touches():
    # 04:00 UTC on 26 November is 17:00 that day in New Zealand; 03:00 UTC on
    # 3 December is 16:00 that day. Eight local dates.
    days = sun_times(utc(2026, 11, 26, 4), utc(2026, 12, 3, 3))
    assert [day["date"] for day in days] == [
        "2026-11-26",
        "2026-11-27",
        "2026-11-28",
        "2026-11-29",
        "2026-11-30",
        "2026-12-01",
        "2026-12-02",
        "2026-12-03",
    ]


def test_local_date_is_used_not_the_utc_date():
    # 13:00 UTC on the 26th is already 02:00 on the 27th in New Zealand.
    days = sun_times(utc(2026, 11, 26, 13), utc(2026, 11, 26, 14))
    assert [day["date"] for day in days] == ["2026-11-27"]


def test_times_are_utc_in_order_and_belong_to_the_local_date():
    for day in sun_times(utc(2026, 11, 26, 4), utc(2026, 12, 3, 3)):
        assert day["dawn"] < day["sunrise"] < day["sunset"] < day["dusk"]
        for name in ("dawn", "sunrise", "sunset", "dusk"):
            assert day[name].tzinfo == UTC
            assert day[name].astimezone(config.NZ).date().isoformat() == day["date"]


def test_summer_times_for_the_bay():
    # 26 November 2026: sunrise about 06:00 and sunset about 20:18, daylight time.
    day = sun_times(utc(2026, 11, 26, 4), utc(2026, 11, 26, 5))[0]
    assert abs(day["sunrise"] - utc(2026, 11, 25, 17, 0)) < CLOSE
    assert abs(day["sunset"] - utc(2026, 11, 26, 7, 18)) < CLOSE


def test_winter_times_for_the_bay():
    # 21 June 2026: sunrise about 07:32 and sunset about 17:15, standard time.
    day = sun_times(utc(2026, 6, 21, 0), utc(2026, 6, 21, 1))[0]
    assert abs(day["sunrise"] - utc(2026, 6, 20, 19, 32)) < CLOSE
    assert abs(day["sunset"] - utc(2026, 6, 21, 5, 15)) < CLOSE


def test_dawn_and_dusk_are_civil_twilight():
    # Civil twilight at this latitude lasts roughly half an hour; nautical nearer an hour.
    day = sun_times(utc(2026, 11, 26, 4), utc(2026, 11, 26, 5))[0]
    assert timedelta(minutes=20) < day["sunrise"] - day["dawn"] < timedelta(minutes=40)
    assert timedelta(minutes=20) < day["dusk"] - day["sunset"] < timedelta(minutes=40)
