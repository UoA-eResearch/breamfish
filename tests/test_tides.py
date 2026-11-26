from datetime import UTC, datetime, timedelta

import pytest

from breamfish import tides


def at(hour, minute=0):
    return datetime(2026, 11, 26, tzinfo=UTC) + timedelta(hours=hour, minutes=minute)


# Low at 00:00, high at 06:00, low at 12:00, high at 18:00.
EVENTS = [
    {"t": at(0), "h": 0.4},
    {"t": at(6), "h": 2.8},
    {"t": at(12), "h": 0.6},
    {"t": at(18), "h": 2.7},
]


def test_high_and_low_come_from_neighbouring_heights():
    labelled = tides.label_high_low(EVENTS)
    assert [event["type"] for event in labelled] == ["low", "high", "low", "high"]
    # The first and last have one neighbour each; starting on a high works too.
    assert [event["type"] for event in tides.label_high_low(EVENTS[1:])] == ["high", "low", "high"]
    # Times and heights are carried through, and the input is not altered.
    assert labelled[1] == {"t": at(6), "h": 2.8, "type": "high"}
    assert "type" not in EVENTS[1]


def test_a_single_event_cannot_be_labelled():
    with pytest.raises(ValueError):
        tides.label_high_low(EVENTS[:1])


def test_height_is_exact_at_the_events():
    assert tides.height_at(EVENTS, at(0)) == pytest.approx(0.4)
    assert tides.height_at(EVENTS, at(6)) == pytest.approx(2.8)
    assert tides.height_at(EVENTS, at(12)) == pytest.approx(0.6)


def test_height_at_the_midpoint_is_halfway():
    assert tides.height_at(EVENTS, at(3)) == pytest.approx(1.6)  # (0.4 + 2.8) / 2
    assert tides.height_at(EVENTS, at(9)) == pytest.approx(1.7)  # (2.8 + 0.6) / 2


def test_height_follows_a_cosine_not_a_straight_line():
    # A quarter of the way up: 0.4 + 2.4 * (1 - cos(45 degrees)) / 2, well short of 1.0.
    assert tides.height_at(EVENTS, at(1, 30)) == pytest.approx(0.7515, abs=1e-4)


def test_rate_is_positive_rising_negative_falling_and_zero_at_the_turn():
    assert tides.rate_at(EVENTS, at(3)) == pytest.approx(0.6283, abs=1e-4)  # 2.4 * pi / 12
    assert tides.rate_at(EVENTS, at(9)) == pytest.approx(-0.5760, abs=1e-4)  # -2.2 * pi / 12
    assert tides.rate_at(EVENTS, at(6)) == pytest.approx(0)
    assert tides.rate_at(EVENTS, at(12)) == pytest.approx(0)


def test_rate_matches_the_slope_of_the_height_curve():
    minute = timedelta(minutes=1)
    for t in (at(1), at(4, 30), at(8), at(15, 20)):
        rise = tides.height_at(EVENTS, t + minute) - tides.height_at(EVENTS, t - minute)
        assert tides.rate_at(EVENTS, t) == pytest.approx(rise * 30, abs=1e-4)  # per hour


def test_no_height_or_rate_outside_the_events():
    assert tides.height_at(EVENTS, at(-1)) is None
    assert tides.height_at(EVENTS, at(19)) is None
    assert tides.rate_at(EVENTS, at(19)) is None
    assert tides.height_at([], at(3)) is None


def test_events_around_keeps_one_before_and_one_after():
    assert tides.events_around(EVENTS, at(7), at(11)) == EVENTS[1:3]
    assert tides.events_around(EVENTS, at(5), at(13)) == EVENTS
    # An event exactly on the edge of the window is enough on that side.
    assert tides.events_around(EVENTS, at(6), at(12)) == EVENTS[1:3]


def test_events_around_makes_do_when_the_window_runs_past_the_data():
    assert tides.events_around(EVENTS, at(-5), at(1)) == EVENTS[:2]
    assert tides.events_around(EVENTS, at(13), at(30)) == EVENTS[2:]
    assert tides.events_around([], at(0), at(1)) == []
