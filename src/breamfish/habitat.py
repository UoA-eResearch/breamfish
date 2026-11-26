"""The habitat index: how well a cell of seabed suits a species, from published evidence.

This is the only place the index is worked out. The site displays what comes out of
here and never recomputes it.

A species file (species/snapper.toml) lists factors. Each factor turns one thing known
about a cell (its depth, its bottom type, its distance from reef) into a suitability
from 0 to 1, by a curve or a table drawn from published studies and cited there. The
index is the weighted geometric mean of the factors, so a cell is only as good as its
factors together, and every cell can show what each factor contributed.

It is a habitat index: it ranks places. It is not a catch probability, and nothing
here knows how many fish there are.

Standard library only: this module runs on the server.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from math import exp, inf, log
from pathlib import Path

SPECIES_DIR = Path(__file__).parent / "species"

# A suitability of exactly 0 would make the whole index 0 whatever the other factors
# say. The curves do reach 0 (snapper are not found at 200 m), and that is meant; but
# the logarithm needs a floor, and this one is far below any class boundary.
FLOOR = 1e-6


@dataclass(frozen=True)
class Factor:
    key: str
    label: str
    input: str  # the seabed layer it reads
    weight: float
    spec: dict = field(repr=False)  # the factor's whole table from the species file

    @property
    def seasonal(self) -> bool:
        return "curve" in self.spec

    def points(self, season: str) -> list[list[float]] | None:
        """The curve as [value, suitability] pairs, or None for a factor scored by class."""
        if "curve" in self.spec:
            return self.spec["curve"][season]["points"]
        return self.spec.get("points")

    def suitability(self, value, season: str) -> float | None:
        """Suitability of one cell's value; None if the factor has nothing to go on.

        value is a number for a curve, or a class key (such as "rock") for a table.
        """
        if value is None:
            return None
        points = self.points(season)
        if points is not None:
            return interpolate(points, value)
        return self.spec["scores"].get(value)


@dataclass(frozen=True)
class Species:
    key: str
    name: str
    scientific_name: str
    factors: tuple[Factor, ...]
    seasons: dict[str, list[int]]
    spec: dict = field(repr=False)

    def season_of(self, month: int) -> str:
        for season, months in self.seasons.items():
            if month in months:
                return season
        raise ValueError(f"no season holds month {month}")


def load_species(key: str, directory: Path = SPECIES_DIR) -> Species:
    spec = tomllib.loads((directory / f"{key}.toml").read_text())
    factors = tuple(
        Factor(f["key"], f["label"], f["input"], float(f["weight"]), f) for f in spec["factor"]
    )
    check(spec, factors)
    return Species(
        spec["key"], spec["name"], spec["scientific_name"], factors, spec["seasons"], spec
    )


def check(spec: dict, factors: tuple[Factor, ...]) -> None:
    """Refuse a species file that would give a wrong index without anyone noticing."""
    months = sorted(m for months in spec["seasons"].values() for m in months)
    if months != list(range(1, 13)):
        raise ValueError("the seasons must hold each month of the year exactly once")
    for factor in factors:
        if factor.weight <= 0:
            raise ValueError(f"{factor.key}: weight must be above zero")
        curves = (
            [factor.points(season) for season in spec["seasons"]]
            if factor.seasonal
            else [factor.points("")]
        )
        for points in curves:
            if points is None:
                scores = factor.spec.get("scores")
                if not scores or not all(0 <= s <= 1 for s in scores.values()):
                    raise ValueError(f"{factor.key}: needs points, or scores from 0 to 1")
                continue
            values = [p[0] for p in points]
            if len(points) < 2 or values != sorted(set(values)):
                raise ValueError(f"{factor.key}: curve values must increase")
            if not all(0 <= p[1] <= 1 for p in points):
                raise ValueError(f"{factor.key}: suitability must be from 0 to 1")
        for item in factor.spec.get("evidence", []):
            if item["ref"] not in spec["reference"]:
                raise ValueError(f"{factor.key}: evidence cites unknown reference {item['ref']}")


def interpolate(points: list[list[float]], value: float) -> float:
    """Straight lines between the points; the end values hold beyond the ends."""
    if value <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        if value <= x1:
            return y0 + (y1 - y0) * (value - x0) / (x1 - x0)
    return points[-1][1]


def combine(parts: dict[str, float | None], weights: dict[str, float]) -> float | None:
    """The weighted geometric mean of the suitabilities that exist.

    parts maps a factor's key to its suitability, or None where it has no data; those
    are left out and the rest carry the mean. None if no factor has anything.
    """
    total = weight = 0.0
    for key, value in parts.items():
        if value is None:
            continue
        total += weights[key] * log(max(value, FLOOR))
        weight += weights[key]
    if weight == 0:
        return None
    return exp(total / weight)


def fifths(values: list[float]) -> list[float]:
    """Four boundaries that split the values into five classes, as near to a fifth each
    as the values allow. A value at or above a boundary is in the class above it.

    Cells with the same value always share a class, and many do: where the curves are
    flat, a third of the bay can have one index. Such a block goes to the class its
    middle falls in, so a large block of average water is classed as the middle, not
    pushed up to the class its lower edge touches. A class nothing reaches leaves its
    boundary at the next one up, or at infinity if nothing is above it.
    """
    ranked = sorted(values)
    n = len(ranked)
    if not n:
        raise ValueError("no values to class")
    breaks = [inf] * 4
    start = 0
    while start < n:
        end = start + 1
        while end < n and ranked[end] == ranked[start]:
            end += 1
        fifth = min(4, int((start + end) / 2 / n * 5))  # 0 is the lowest class
        for boundary in range(fifth):
            breaks[boundary] = min(breaks[boundary], ranked[start])
        start = end
    return breaks


def class_of(value: float, breaks: list[float]) -> int:
    """1 (lowest) to len(breaks) + 1 (highest)."""
    return 1 + sum(value >= b for b in breaks)


# --- Checking the index against places snapper were recorded ------------------------------


def auc(present: list[float], background: list[float]) -> float:
    """The chance that the index at a place where the species was recorded is higher
    than at a place picked at random from the background (a tie counts half).

    0.5 is no better than chance; 1 means every record sits above all the background.
    """
    from bisect import bisect_left, bisect_right

    ranked = sorted(background)
    n = len(ranked)
    if not present or not n:
        raise ValueError("needs records and a background")
    below = sum((bisect_left(ranked, v) + bisect_right(ranked, v)) / 2 for v in present)
    return below / (n * len(present))
