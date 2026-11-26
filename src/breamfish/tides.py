"""The tide curve between predicted high and low waters.

An event is a dict {"t": datetime in UTC, "h": height in metres}; label_high_low adds
"type". Lists of events are always in time order.
"""

import math
from datetime import timedelta
from itertools import pairwise


def label_high_low(events: list[dict]) -> list[dict]:
    """Add "type": "high" or "low" to each event by comparing it with its neighbours."""
    labelled = []
    for i, event in enumerate(events):
        neighbours = [events[j]["h"] for j in (i - 1, i + 1) if 0 <= j < len(events)]
        if not neighbours:
            raise ValueError("cannot tell high from low with a single tide event")
        is_high = event["h"] > sum(neighbours) / len(neighbours)
        labelled.append({**event, "type": "high" if is_high else "low"})
    return labelled


def events_around(events: list[dict], start, end) -> list[dict]:
    """The events from the last one at or before start to the first at or after end."""
    first = max((i for i, e in enumerate(events) if e["t"] <= start), default=0)
    last = min((i for i, e in enumerate(events) if e["t"] >= end), default=len(events) - 1)
    return events[first : last + 1]


def bracket(events: list[dict], t):
    """The two events either side of t, or None if t is outside the list."""
    for before, after in pairwise(events):
        if before["t"] <= t <= after["t"]:
            return before, after
    return None


def height_at(events: list[dict], t):
    """Tide height in metres at time t: a half cosine wave between the two events."""
    pair = bracket(events, t)
    if pair is None:
        return None
    before, after = pair
    phase = math.pi * ((t - before["t"]) / (after["t"] - before["t"]))
    return before["h"] + (after["h"] - before["h"]) * (1 - math.cos(phase)) / 2


def rate_at(events: list[dict], t):
    """Rate of change in metres per hour at time t, positive when the tide is rising.

    This is the slope of the curve in height_at, so it is zero at high and low water.
    """
    pair = bracket(events, t)
    if pair is None:
        return None
    before, after = pair
    span_hours = (after["t"] - before["t"]) / timedelta(hours=1)
    phase = math.pi * ((t - before["t"]) / (after["t"] - before["t"]))
    return (after["h"] - before["h"]) * math.pi / (2 * span_hours) * math.sin(phase)
