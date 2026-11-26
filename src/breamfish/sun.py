"""Civil dawn, sunrise, sunset and civil dusk for the bay."""

from datetime import UTC, timedelta

from astral import Observer
from astral.sun import sun

from breamfish import config


def sun_times(first_hour, last_hour) -> list[dict]:
    """One entry per local calendar date between two UTC times, with the times in UTC.

    Dates are New Zealand dates: sunrise on the 26th local is still the 25th in UTC.
    """
    observer = Observer(latitude=config.SUN_LAT, longitude=config.SUN_LON)
    day = first_hour.astimezone(config.NZ).date()
    last_day = last_hour.astimezone(config.NZ).date()
    days = []
    while day <= last_day:
        # Passing the local timezone makes astral return the events of that local date.
        # Its dawn and dusk are civil ones (sun 6 degrees below the horizon) by default.
        times = sun(observer, date=day, tzinfo=config.NZ)
        entry = {"date": day.isoformat()}
        for name in ("dawn", "sunrise", "sunset", "dusk"):
            entry[name] = times[name].astimezone(UTC)
        days.append(entry)
        day += timedelta(days=1)
    return days
