from datetime import UTC, datetime, timedelta

import pytest
from conftest import NOW, fake_get

from breamfish import config, tides
from breamfish.sources import linz_tides

HEADING = (
    "﻿079,Marsden Point,35°50'S,174°30'E   \r\n"
    "Based on constituent set with reference date:,01-Jan-2016\r\n"
    "Local Std or Daylight Time,Tidal heights in metres.\r\n"
)


def csv_body(*rows: str) -> bytes:
    """A tide file like the real ones: byte order mark, three heading lines, CRLF."""
    return (HEADING + "".join(row + "\r\n" for row in rows)).encode("utf-8")


def utc(*args):
    return datetime(*args, tzinfo=UTC)


def local_date(event):
    return event["t"].astimezone(config.NZ).date().isoformat()


# --- parsing ------------------------------------------------------------------------


def test_fixture_really_has_a_byte_order_mark_and_parses(tide_csv):
    assert tide_csv.startswith(b"\xef\xbb\xbf")  # guards against the fixture being "tidied"
    events = linz_tides.parse_csv(tide_csv)
    assert len(events) == 62
    assert events == sorted(events, key=lambda event: event["t"])


def test_a_byte_order_mark_right_before_a_data_row_is_dropped():
    body = b"\xef\xbb\xbf26,Th,11,2026,03:04,0.4,09:28,2.8\r\nLocal Std or Daylight Time\r\n"
    assert len(linz_tides.parse_csv(body)) == 2


def test_empty_trailing_pair_is_skipped(tide_csv):
    # 1,Th,1,2026,06:01,2.5,12:06,0.8,18:15,2.5,,
    new_years_day = [e for e in linz_tides.parse_csv(tide_csv) if local_date(e) == "2026-01-01"]
    assert [event["h"] for event in new_years_day] == [2.5, 0.8, 2.5]


def test_daylight_time_is_utc_plus_13(tide_csv):
    # 26,Th,11,2026,03:04,0.4,09:28,2.8,...  09:28 NZDT is 20:28 UTC the day before.
    events = linz_tides.parse_csv(tide_csv)
    assert {"t": utc(2026, 11, 25, 20, 28), "h": 2.8} in events
    assert {"t": utc(2026, 11, 25, 14, 4), "h": 0.4} in events


def test_standard_time_is_utc_plus_12(tide_csv):
    # 1,We,7,2026,02:15,0.9,08:17,2.4,...  02:15 NZST is 14:15 UTC the day before.
    events = linz_tides.parse_csv(tide_csv)
    assert {"t": utc(2026, 6, 30, 14, 15), "h": 0.9} in events
    assert {"t": utc(2026, 6, 30, 20, 17), "h": 2.4} in events


def test_high_and_low_inferred_for_real_rows(tide_csv):
    late_november = [e for e in linz_tides.parse_csv(tide_csv) if e["t"] > utc(2026, 11, 1)]
    labelled = tides.label_high_low(late_november)
    on_the_26th = [(e["h"], e["type"]) for e in labelled if local_date(e) == "2026-11-26"]
    assert on_the_26th == [(0.4, "low"), (2.8, "high"), (0.6, "low"), (2.7, "high")]
    # The 29th has only three tides; highs and lows still alternate through it.
    kinds = [event["type"] for event in labelled]
    assert all(a != b for a, b in zip(kinds, kinds[1:], strict=False))


def test_a_file_that_is_not_a_tide_table_is_rejected():
    with pytest.raises(ValueError):
        linz_tides.parse_csv(b"<html>Service unavailable</html>")
    with pytest.raises(ValueError):  # the heading is there but no rows are
        linz_tides.parse_csv(csv_body())
    with pytest.raises(ValueError):  # rows without the heading that says times are local
        linz_tides.parse_csv(b"26,Th,11,2026,03:04,0.4,09:28,2.8\r\n")


# --- the hour that happens twice when the clocks go back ------------------------------


def test_repeated_hour_real_case_is_the_first_reading():
    # Clocks went back at 03:00 on 6 April 2025, so 02:47 happened twice. The tide
    # before it was 20:19 NZDT; only the first (daylight time) reading is ~6 h later.
    events = linz_tides.parse_csv(
        csv_body(
            "5,Sa,4,2025,01:47,2.7,08:00,0.8,14:10,2.5,20:19,0.8",
            "6,Su,4,2025,02:47,2.6,08:02,0.9,14:11,2.4,20:20,0.9",
        )
    )
    assert events[4] == {"t": utc(2025, 4, 5, 13, 47), "h": 2.6}
    assert events[5] == {"t": utc(2025, 4, 5, 20, 2), "h": 0.9}  # 08:02 NZST


def test_repeated_hour_can_be_the_second_reading():
    # After a tide at 21:40 NZDT (08:40 UTC), the next is due near 14:52 UTC, which is
    # 02:52 NZST: the second time the clock showed 02:52 on 5 April 2026.
    local = datetime(2026, 4, 5, 2, 52, tzinfo=config.NZ)
    assert linz_tides.to_utc(local, previous=utc(2026, 4, 4, 8, 40)) == utc(2026, 4, 4, 14, 52)
    assert linz_tides.to_utc(local, previous=utc(2026, 4, 4, 7, 40)) == utc(2026, 4, 4, 13, 52)
    assert linz_tides.to_utc(local, previous=None) == utc(2026, 4, 4, 13, 52)


# --- which year files to fetch ------------------------------------------------------


def test_one_year_file_on_an_ordinary_day():
    assert linz_tides.years_needed(utc(2026, 11, 26, 4), utc(2026, 12, 3, 3)) == [2026]
    assert linz_tides.years_needed(utc(2026, 12, 22, 10), utc(2026, 12, 29, 9)) == [2026]


def test_two_year_files_when_the_window_reaches_new_year():
    # Ends 22:00 on 31 December local time; the tide after that may be on 1 January.
    assert linz_tides.years_needed(utc(2026, 12, 24, 10), utc(2026, 12, 31, 9)) == [2026, 2027]
    # Starts 01:00 on 1 January local time; the tide before that was on 31 December.
    assert linz_tides.years_needed(utc(2026, 12, 31, 12), utc(2027, 1, 7, 11)) == [2026, 2027]
    assert linz_tides.years_needed(utc(2027, 1, 3, 0), utc(2027, 1, 9, 23)) == [2027]


# --- fetching -----------------------------------------------------------------------

DECEMBER_2026 = csv_body(
    "30,We,12,2026,01:04,2.6,07:07,0.6,13:30,2.7,19:47,0.6",
    "31,Th,12,2026,01:59,2.5,08:00,0.7,14:21,2.6,20:40,0.7",
)
JANUARY_2027 = csv_body(
    "1,Fr,1,2027,02:55,2.4,08:56,0.8,15:13,2.5,21:33,0.7",
    "2,Sa,1,2027,03:53,2.4,09:54,0.9,16:06,2.4,22:27,0.8",
)
NEW_YEAR_WINDOW = (utc(2026, 12, 30, 0), utc(2026, 12, 31, 23))


def test_window_across_new_year_joins_two_files(tmp_path):
    calls = []
    get = fake_get({"Point%202026.csv": DECEMBER_2026, "Point%202027.csv": JANUARY_2027}, calls)

    result = linz_tides.fetch_events(get, tmp_path, *NEW_YEAR_WINDOW, now=utc(2026, 12, 30, 0, 5))

    assert [url[-8:] for url in calls] == ["2026.csv", "2027.csv"]
    events = result["data"]
    assert len(events) == 16
    # 20:40 on 31 December and 02:55 on 1 January, both NZDT, are neighbours.
    assert events[7] == {"t": utc(2026, 12, 31, 7, 40), "h": 0.7, "type": "low"}
    assert events[8] == {"t": utc(2026, 12, 31, 13, 55), "h": 2.4, "type": "high"}
    assert result["stale"] is False
    assert result["fetched_at"] == utc(2026, 12, 30, 0, 5)
    assert result["message"] == ""


def test_a_missing_year_still_gives_the_events_we_have(tmp_path):
    get = fake_get({"2026.csv": DECEMBER_2026, "2027.csv": RuntimeError("404 Not Found")})

    result = linz_tides.fetch_events(get, tmp_path, *NEW_YEAR_WINDOW, now=utc(2026, 12, 30))

    assert len(result["data"]) == 8
    assert result["message"].startswith("2027: fetch failed")


def test_tide_file_is_not_fetched_again_within_a_week(tmp_path, tide_csv):
    calls = []
    get = fake_get({"2026.csv": tide_csv}, calls)
    window = (utc(2026, 11, 26, 4), utc(2026, 12, 3, 3))

    linz_tides.fetch_events(get, tmp_path, *window, now=NOW)
    again = linz_tides.fetch_events(get, tmp_path, *window, now=NOW + timedelta(days=6))
    assert len(calls) == 1
    assert again["stale"] is False  # reusing it by design is not a fallback
    assert again["fetched_at"] == NOW

    linz_tides.fetch_events(get, tmp_path, *window, now=NOW + timedelta(days=8))
    assert len(calls) == 2


def test_cached_tide_file_covers_an_outage_for_60_days(tmp_path, tide_csv):
    window = (utc(2026, 11, 26, 4), utc(2026, 12, 3, 3))
    linz_tides.fetch_events(fake_get({"2026.csv": tide_csv}), tmp_path, *window, now=NOW)
    down = fake_get({"2026.csv": RuntimeError("connection refused")})

    after_30_days = linz_tides.fetch_events(down, tmp_path, *window, now=NOW + timedelta(days=30))
    assert after_30_days["stale"] is True
    assert len(after_30_days["data"]) == 62
    assert after_30_days["fetched_at"] == NOW

    after_61_days = linz_tides.fetch_events(down, tmp_path, *window, now=NOW + timedelta(days=61))
    assert after_61_days["data"] is None
    assert after_61_days["fetched_at"] is None
