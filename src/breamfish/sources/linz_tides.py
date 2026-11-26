"""LINZ tide predictions for Marsden Point: one CSV per calendar year."""

import csv
from datetime import UTC, datetime, timedelta

from breamfish import config, tides
from breamfish.sources.fetch import fetch_cached

# High and low water are about this far apart: half of the 12 h 25 min lunar tide.
USUAL_GAP = timedelta(hours=6, minutes=12)


def years_needed(first_hour, last_hour) -> list[int]:
    """The calendar years (New Zealand time) whose files the window needs.

    The day's margin at each end guarantees a tide before the first hour and one after
    the last. Around New Year that means two files.
    """
    first = (first_hour - timedelta(days=1)).astimezone(config.NZ).year
    last = (last_hour + timedelta(days=1)).astimezone(config.NZ).year
    return list(range(first, last + 1))


def to_utc(local: datetime, previous: datetime | None) -> datetime:
    """New Zealand wall-clock time to UTC.

    One hour each April happens twice, when the clocks go back. A tide in that hour
    could be either; take the reading that keeps the usual gap from the previous tide.
    """
    first = local.astimezone(UTC)
    second = local.replace(fold=1).astimezone(UTC)
    if first == second or previous is None:
        return first
    return min(first, second, key=lambda t: abs(t - previous - USUAL_GAP))


def parse_csv(body: bytes) -> list[dict]:
    """Parse one year's file into events {"t": UTC datetime, "h": metres}, in time order.

    The file starts with a UTF-8 byte order mark and three heading lines. A data row is
        26,Th,11,2026,03:04,0.4,09:28,2.8,15:34,0.6,21:44,2.7
    that is day, weekday, month, year, then up to four time,height pairs. A day with
    only three tides ends in two empty fields. Times are New Zealand local time, NOT
    UTC. The file does not say which tides are high; see tides.label_high_low.
    """
    text = body.decode("utf-8-sig")  # "-sig" drops the byte order mark
    if "Local Std or Daylight Time" not in text:
        raise ValueError("heading no longer says the times are local: has the format changed?")

    events = []
    for row in csv.reader(text.splitlines()):
        if len(row) < 6 or not row[0].strip().isdigit():
            continue  # a heading line
        day, month, year = int(row[0]), int(row[2]), int(row[3])
        for clock, height in zip(row[4::2], row[5::2], strict=False):
            if not clock or not height:
                continue  # an empty trailing pair
            hour, minute = clock.split(":")
            local = datetime(year, month, day, int(hour), int(minute), tzinfo=config.NZ)
            previous = events[-1]["t"] if events else None
            events.append({"t": to_utc(local, previous), "h": float(height)})
    if not events:
        raise ValueError("no tide rows found")
    return events


def fetch_events(get, cache_dir, first_hour, last_hour, now) -> dict:
    """Get every tide event the window needs, each labelled high or low.

    Returns a dict shaped like a fetch_cached result. With two year files in play,
    fetched_at is the older fetch and stale is True if either came from a fallback.
    """
    events, fetch_times, notes, stale = [], [], [], False
    for year in years_needed(first_hour, last_hour):
        result = fetch_cached(
            get,
            cache_dir,
            f"linz_marsden_point_{year}.csv",
            config.TIDE_URL.format(year=year),
            None,
            parse=parse_csv,
            now=now,
            max_age=config.TIDE_MAX_AGE,
            refetch_after=config.TIDE_REFETCH_AFTER,
        )
        if result["data"] is not None:
            events += result["data"]
            fetch_times.append(result["fetched_at"])
        stale = stale or result["stale"]
        if result["message"]:
            notes.append(f"{year}: {result['message']}")

    events.sort(key=lambda event: event["t"])
    usable = len(events) >= 2
    return {
        "data": tides.label_high_low(events) if usable else None,
        "fetched_at": min(fetch_times) if usable else None,
        "stale": stale,
        "message": "; ".join(notes),
    }
