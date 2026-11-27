"""Check a build against the charted soundings and write the result down.

A charted sounding is one measured depth at a point; a grid cell is the mean over a
hectare. Charts also favour the shallowest sounding in a patch (it is the one that
matters to a keel), so on uneven ground a cell is expected to read a little deeper than
the soundings in it. Agreement within a metre or so on flat ground is as good as this
comparison gets.
"""

from __future__ import annotations

import warnings

import numpy as np

from seabed import bottom, depth, grid

# Soundings are grouped by their own depth, in metres below chart datum.
DEPTH_BANDS_M = (-5, 5, 10, 20, 25, 30, 40, 60, 200)


def _at_soundings(cells: np.ndarray, soundings: np.ndarray):
    """(cell value, sounding depth, row, col, index) for soundings in cells that have a value."""
    rows, cols = grid.cell_of(soundings[:, 0], soundings[:, 1])
    index = np.nonzero(grid.inside(rows, cols))[0]
    rows, cols = rows[index], cols[index]
    have = ~np.isnan(cells[rows, cols])
    rows, cols, index = rows[have], cols[have], index[have]
    return cells[rows, cols], soundings[index, 2], rows, cols, index


def compare(cells: np.ndarray, soundings: np.ndarray, bands) -> list[dict]:
    """Grid minus sounding, summarised for each band of sounding depth."""
    value, sounded, *_ = _at_soundings(cells, soundings)
    difference = value - sounded
    rows = []
    for low, high in zip(bands[:-1], bands[1:], strict=True):
        d = difference[(sounded >= low) & (sounded < high)]
        if len(d) == 0:
            continue
        rows.append(
            {
                "from_m": low,
                "to_m": high,
                "soundings": int(len(d)),
                "median_m": round(float(np.median(d)), 2),
                "median_abs_m": round(float(np.median(np.abs(d))), 2),
                "p90_abs_m": round(float(np.percentile(np.abs(d), 90)), 2),
            }
        )
    return rows


# Survey periods found in the chart's "quality of data" areas for this bay.
SURVEY_PERIODS = ((1, 1970, "1955 to 1962"), (1970, 1990, "1981 to 1982"), (1990, 9999, "1999 on"))


def compare_at_points(fine_depth, res_m: int, soundings, survey_year) -> list[dict]:
    """A fine raster minus each sounding at the sounding's own fine cell, by survey period.

    Sharper than the cell comparison: no averaging over a hectare. "Flat" keeps only
    soundings where the raster varies by under 0.3 m across the 50 m around them, which
    takes most of the chart's shoal bias out. What is left is the two surveys
    disagreeing, a datum error, or the seabed having moved.
    """
    rows = np.floor((grid.NORTH_N - soundings[:, 1]) / res_m).astype(int)
    cols = np.floor((soundings[:, 0] - grid.WEST_E) / res_m).astype(int)
    ok = (rows >= 2) & (rows < fine_depth.shape[0] - 2)
    ok &= (cols >= 2) & (cols < fine_depth.shape[1] - 2)
    rows, cols, sounded = rows[ok], cols[ok], soundings[ok, 2]
    cell_rows, cell_cols = grid.cell_of(soundings[ok, 0], soundings[ok, 1])
    year = survey_year[cell_rows, cell_cols]
    here = fine_depth[rows, cols]
    around = np.stack(
        [fine_depth[rows + dr, cols + dc] for dr in range(-2, 3) for dc in range(-2, 3)], axis=1
    )
    with np.errstate(invalid="ignore"):
        flat = (around.max(axis=1) - around.min(axis=1)) < 0.3  # NaN anywhere: not flat
    have = ~np.isnan(here)
    out = []
    for first, last, label in SURVEY_PERIODS:
        period = have & (year >= first) & (year < last)
        for name, mask in (("all", period), ("flat", period & flat)):
            d = (here - sounded)[mask]
            if len(d):
                out.append(
                    {
                        "survey": label,
                        "ground": name,
                        "soundings": int(len(d)),
                        "median_m": round(float(np.median(d)), 2),
                        "quartiles_m": [round(float(np.percentile(d, q)), 2) for q in (25, 75)],
                    }
                )
    return out


def overlap(a: np.ndarray, b: np.ndarray) -> dict:
    """How two depth grids compare in the cells both cover (a minus b)."""
    both = ~np.isnan(a) & ~np.isnan(b)
    if not both.any():
        return {"cells": 0}
    d = (a - b)[both]
    return {
        "cells": int(both.sum()),
        "median_m": round(float(np.median(d)), 2),
        "median_abs_m": round(float(np.median(np.abs(d))), 2),
        "p90_abs_m": round(float(np.percentile(np.abs(d), 90)), 2),
    }


def spot_checks(merged, source, soundings, to_lonlat, per_source: int = 4) -> list[dict]:
    """A few individual soundings for each depth source, spread from west to east."""
    value, sounded, rows, cols, index = _at_soundings(merged, soundings)
    label = {src.code: src.label for src in depth.SOURCES}
    checks = []
    for src in depth.SOURCES:
        mine = np.nonzero(source[rows, cols] == src.code)[0]
        if len(mine) == 0:
            continue
        mine = mine[np.argsort(soundings[index[mine], 0], kind="stable")]
        picks = mine[np.linspace(0, len(mine) - 1, min(per_source, len(mine))).astype(int)]
        lon, lat = to_lonlat(soundings[index[picks], 0], soundings[index[picks], 1])
        for i, x, y in zip(picks, lon, lat, strict=True):
            checks.append(
                {
                    "lon": round(float(x), 4),
                    "lat": round(float(y), 4),
                    "sounding_m": round(float(sounded[i]), 1),
                    "grid_m": round(float(value[i]), 1),
                    "difference_m": round(float(value[i] - sounded[i]), 1),
                    "source": label[src.code],
                }
            )
    return checks


def cell_counts(grids) -> dict:
    by_source = {src.key: int((grids.source == src.code).sum()) for src in depth.SOURCES}
    by_quality: dict = {}
    for src in depth.SOURCES:
        key = depth.QUALITY[src.quality]["key"]
        by_quality[key] = by_quality.get(key, 0) + by_source[src.key]
    sea = grids.source != 0
    by_bottom = {
        cls["key"]: int(((grids.bottom == cls["code"]) & sea).sum()) for cls in bottom.CLASSES
    }
    return {
        "sea": int(sea.sum()),
        "source": by_source,
        "quality": by_quality,
        "bottom": by_bottom,
        "with_slope": int((~np.isnan(grids.slope)).sum()),
    }


def _table(header: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def _bands_table(rows: list[dict]) -> str:
    if not rows:
        return "No charted soundings fall in cells of this source."
    return _table(
        [
            "Sounding depth (m)",
            "Soundings",
            "Median difference (m)",
            "Median size (m)",
            "90% within (m)",
        ],
        [
            [
                f"{r['from_m']} to {r['to_m']}",
                r["soundings"],
                f"{r['median_m']:+.2f}",
                r["median_abs_m"],
                r["p90_abs_m"],
            ]
            for r in rows
        ],
    )


def markdown(facts: dict, lidar_max_depth_m: float) -> str:
    cells = facts["cells"]
    sea = max(cells["sea"], 1)
    share = lambda n: f"{100 * n / sea:.1f}%"  # noqa: E731
    labels = {src.key: src.label for src in depth.SOURCES}
    quality = {q["key"]: q["label"] for q in depth.QUALITY}
    kinds = {cls["key"]: cls["label"] for cls in bottom.CLASSES}
    both = facts["lidar_multibeam_overlap"]
    parts = [
        "# Seabed build report",
        "",
        "Written by `scripts/build_seabed.py`; do not edit by hand. It describes the grids "
        "committed under `web/public/seabed/`. The method is in [seabed.md](seabed.md).",
        "",
        "Differences are grid minus sounding, in metres: positive means the grid is deeper. "
        "A cell is a mean over one hectare and a sounding is one point, usually the "
        "shallowest in its patch, so a small positive difference is expected.",
        "",
        f"## Where the depth comes from ({cells['sea']:,} sea cells of one hectare)",
        "",
        _table(
            ["Source", "Cells", "Share of sea"],
            [[labels[k], f"{n:,}", share(n)] for k, n in cells["source"].items()],
        ),
        "",
        _table(
            ["Quality class", "Cells", "Share of sea"],
            [[quality[k], f"{n:,}", share(n)] for k, n in cells["quality"].items()],
        ),
        "",
        f"Slope and roughness exist for {cells['with_slope']:,} cells "
        f"({share(cells['with_slope'])}).",
        "",
        "## LiDAR against charted soundings",
        "",
        "Every charted sounding that falls in a cell the LiDAR covers, before any depth "
        "limit is applied.",
        "",
        _bands_table(facts["lidar_check"]),
        "",
        "The same soundings against the 10 m LiDAR cell each one falls in, grouped by when "
        "the chart says the area was surveyed. Flat ground is where the LiDAR varies by "
        "under 0.3 m across the 50 m around the sounding.",
        "",
        _table(
            ["Chart survey", "Ground", "Soundings", "Median difference (m)", "Middle half (m)"],
            [
                [
                    r["survey"],
                    r["ground"],
                    r["soundings"],
                    f"{r['median_m']:+.2f}",
                    f"{r['quartiles_m'][0]:+.2f} to {r['quartiles_m'][1]:+.2f}",
                ]
                for r in facts["lidar_check_by_survey"]
            ],
        ),
        "",
        f"LiDAR deeper than {lidar_max_depth_m:g} m below chart datum is not used: "
        f"{facts['lidar_cells_dropped_as_too_deep']:,} cells were dropped for that reason.",
        "",
        "## Multibeam against charted soundings",
        "",
        _bands_table(facts["multibeam_check"]),
        "",
        "## LiDAR against multibeam",
        "",
        (
            f"The two overlap in {both['cells']:,} cells. LiDAR minus multibeam: median "
            f"{both['median_m']:+.2f} m, median size {both['median_abs_m']} m, 90% within "
            f"{both['p90_abs_m']} m."
            if both["cells"]
            else "The two do not overlap."
        ),
        "",
        "## The merged grid against charted soundings",
        "",
        "All sources together. Where the depth is from the chart this is not an independent "
        "test: the surface was drawn through these soundings.",
        "",
        _bands_table(facts["final_check"]),
        "",
        "## Spot checks",
        "",
        _table(
            [
                "Longitude",
                "Latitude",
                "Charted sounding (m)",
                "Grid (m)",
                "Difference (m)",
                "Grid source",
            ],
            [
                [
                    c["lon"],
                    c["lat"],
                    c["sounding_m"],
                    c["grid_m"],
                    f"{c['difference_m']:+.1f}",
                    c["source"],
                ]
                for c in facts["spot_checks"]
            ],
        ),
        "",
        "## Bottom type",
        "",
        _table(
            ["Class", "Cells", "Share of sea"],
            [[kinds[k], f"{n:,}", share(n)] for k, n in cells["bottom"].items()],
        ),
        "",
    ]
    return "\n".join(parts)


# --- Rough ground ---------------------------------------------------------------------------
#
# Written by scripts/build_relief.py, as the last section of the same report. The seabed
# build keeps the section when it rewrites the rest.

ROUGH_GROUND_HEADING = "## Rough ground from the 2 m LiDAR"
ROUGH_THRESHOLDS_M = (0.10, 0.15, 0.20, 0.30)
ROUGH_DEPTH_BANDS_M = (-3, 5, 10, 20, 30, 40)
PUBLISHED_MEASURE = "Rough ground, as published: the third roughest 10 m square"
GRID_ROUGHNESS_MEASURE = "Roughness of the 100 m grid: about one plane through the cell"
# Two ways of scoring that differ by less than this in AUC are not told apart by labels
# this few: with some hundreds of cells a side, an AUC is good to about two hundredths.
AUC_TIE = 0.02


def auc(score: np.ndarray, positive: np.ndarray, negative: np.ndarray) -> float | None:
    """The chance that a cell picked from positive scores higher than one picked from
    negative, ties counting half. 0.5 is no better than a coin; None if either is empty."""
    from scipy.stats import rankdata

    have = ~np.isnan(score)
    high, low = score[positive & have], score[negative & have]
    if len(high) == 0 or len(low) == 0:
        return None
    ranks = rankdata(np.concatenate([high, low]))
    above = ranks[: len(high)].sum() - len(high) * (len(high) + 1) / 2
    return round(float(above / (len(high) * len(low))), 3)


def _spread(values: np.ndarray) -> dict:
    values = values[~np.isnan(values)]
    if len(values) == 0:
        return {"cells": 0}
    low, lower, middle, upper, high = np.percentile(values, [10, 25, 50, 75, 90])
    return {
        "cells": int(len(values)),
        "p10_m": round(float(low), 2),
        "p25_m": round(float(lower), 2),
        "median_m": round(float(middle), 2),
        "p75_m": round(float(upper), 2),
        "p90_m": round(float(high), 2),
    }


def rough_ground(windows, fine, cell_depth, roughness, slope, kind, kind_source) -> dict:
    """How well rough ground tells rock from soft bottom, where both maps and LiDAR speak.

    windows is the roughness of every 10 m square; fine is the layer made from it, as it
    is published; the rest are the 100 m grids as committed. Two sets of labels, neither of them
    the truth: the chart (cells it marks as rock against cells with a charted sample of
    sand or mud) and the habitat map (rock against soft sediment).
    """
    from seabed import relief

    have = ~np.isnan(fine)
    charted = kind_source != bottom.HABITAT_MAP
    soft = np.isin(kind, [bottom.SAND, bottom.MUD])
    groups = {
        "chart_rock": have & (kind == bottom.ROCK) & (kind_source == bottom.CHART_ROCK),
        "chart_soft": have & soft & (kind_source == bottom.CHART_SAMPLE),
        "habitat_rock": have & (kind == bottom.ROCK) & ~charted,
        "habitat_soft": have & (soft | (kind == bottom.SOFT)) & ~charted,
    }
    cells, enough = relief.cell_windows(windows)
    with warnings.catch_warnings():
        # numpy warns about a cell with no windows at all; those cells are masked anyway.
        warnings.simplefilter("ignore", RuntimeWarning)
        roughest = np.where(enough, np.nanmax(cells, axis=2), np.nan)
        mean = np.where(enough, np.nanmean(cells, axis=2), np.nan)
        median = np.where(enough, np.nanmedian(cells, axis=2), np.nan)
    # To the centimetre, like the published layer, so that all of them tie alike.
    measures = {
        PUBLISHED_MEASURE: fine,
        "The roughest 10 m square": np.round(roughest, 2),
        "The tenth roughest 10 m square": np.round(relief.cell_roughness(windows, 10), 2),
        "The mean of the 10 m squares": np.round(mean, 2),
        "The median of the 10 m squares": np.round(median, 2),
        GRID_ROUGHNESS_MEASURE: roughness,
        "Slope of the 100 m grid": slope,
    }
    not_rock = have & (kind != bottom.ROCK)
    return {
        "cells": int(have.sum()),
        "groups": {key: _spread(fine[mask]) for key, mask in groups.items()},
        "everywhere": _spread(fine[have]),
        "auc": [
            {
                "measure": label,
                "chart": auc(score, groups["chart_rock"], groups["chart_soft"]),
                "habitat": auc(score, groups["habitat_rock"], groups["habitat_soft"]),
            }
            for label, score in measures.items()
        ],
        "thresholds": [
            {
                "above_m": threshold,
                **{key: int((fine[mask] > threshold).sum()) for key, mask in groups.items()},
            }
            for threshold in ROUGH_THRESHOLDS_M
        ],
        "floor_by_depth": [
            {"from_m": low, "to_m": high, **_spread(fine[not_rock & in_band])}
            for low, high in zip(ROUGH_DEPTH_BANDS_M[:-1], ROUGH_DEPTH_BANDS_M[1:], strict=True)
            for in_band in [(cell_depth >= low) & (cell_depth < high)]
        ],
    }


def without_rough_ground(text: str) -> str:
    """A report with the rough-ground section taken off its end."""
    at = text.find(ROUGH_GROUND_HEADING)
    return text if at < 0 else text[:at]


def rough_ground_section(text: str) -> str:
    """The rough-ground section of a report, or nothing if it has none."""
    at = text.find(ROUGH_GROUND_HEADING)
    return "" if at < 0 else text[at:]


def joined(main: str, rough_ground: str) -> str:
    """The seabed build's report with the relief build's section after it."""
    if not rough_ground:
        return main
    return main.rstrip("\n") + "\n\n" + rough_ground if main.strip() else rough_ground


def rough_ground_reading(rough: dict) -> str:
    """One line for the site on what a value means, from this build's own numbers."""
    groups, line = rough["groups"], rough["thresholds"][0]
    soft, rock = groups["chart_soft"]["cells"], groups["chart_rock"]["cells"]
    if not soft or not rock:
        return ""
    return (
        f"Under {line['above_m']:.2f} m in {100 * (soft - line['chart_soft']) / soft:.0f}% of "
        f"the cells with a charted sample of sand or mud; over it in "
        f"{100 * line['chart_rock'] / rock:.0f}% of the cells charted as rock."
    )


def shade_agreement(lidar_stored: np.ndarray, multibeam_shade: np.ndarray) -> dict:
    """Do the two surveys show the same shapes where both measured the same seabed?

    lidar_stored is the LiDAR's stored shade on its fine grid; multibeam_shade is the
    multibeam's signed shade on its coarser one, before the LiDAR's cover is cut out of
    it. The LiDAR's shade is averaged over each multibeam cell it all but fills, and the
    two are correlated.
    """
    from seabed import relief

    factor = lidar_stored.shape[0] // multibeam_shade.shape[0]
    rows, cols = multibeam_shade.shape
    blocks = lidar_stored.reshape(rows, factor, cols, factor)
    valid = blocks != relief.NO_SHADE
    count = valid.sum(axis=(1, 3))
    total = np.where(valid, blocks, 0).sum(axis=(1, 3), dtype=np.float64)
    both = (count >= 0.9 * factor * factor) & ~np.isnan(multibeam_shade)
    if both.sum() < 3:
        return {"cells": int(both.sum())}
    lidar = total[both] / count[both] / 127
    if lidar.std() == 0 or multibeam_shade[both].std() == 0:
        return {"cells": int(both.sum())}
    return {
        "cells": int(both.sum()),
        "cell_m": int(round(grid.CELL_M * grid.NROWS / rows)),
        "correlation": round(float(np.corrcoef(lidar, multibeam_shade[both])[0, 1]), 2),
    }


def _spread_row(label: str, spread: dict) -> list:
    if not spread["cells"]:
        return [label, 0, "", "", "", "", ""]
    return [
        label,
        f"{spread['cells']:,}",
        *(f"{spread[key]:.2f}" for key in ("p10_m", "p25_m", "median_m", "p75_m", "p90_m")),
    ]


def _share(count: int, of: int) -> str:
    return f"{count:,} ({100 * count / of:.0f}%)" if of else "0"


def _verdict(facts: dict) -> str:
    """What the numbers say about using rough ground as a source of bottom type. Worded
    from the numbers of this build, so it cannot outlive them."""
    by_measure = {row["measure"]: row for row in facts["auc"]}
    fine, coarse = by_measure[PUBLISHED_MEASURE], by_measure[GRID_ROUGHNESS_MEASURE]
    if fine["chart"] is None or coarse["chart"] is None:
        return (
            "There are no cells with both a charted bottom and LiDAR to test it on, so "
            "nothing here supports using it as a source of bottom type."
        )
    gap = fine["chart"] - coarse["chart"]
    if gap > AUC_TIE:
        compared = (
            f"It tells charted rock from charted sand and mud better than the roughness the "
            f"100 m grid already has ({fine['chart']:.2f} against {coarse['chart']:.2f})"
        )
    elif gap < -AUC_TIE:
        compared = (
            f"It tells charted rock from charted sand and mud less well than the roughness "
            f"the 100 m grid already has ({fine['chart']:.2f} against {coarse['chart']:.2f})"
        )
    else:
        compared = (
            f"It tells charted rock from charted sand and mud about as well as the roughness "
            f"the 100 m grid already has ({fine['chart']:.2f} against {coarse['chart']:.2f}), "
            "and no better"
        )
    groups, lowest = facts["groups"], facts["thresholds"][0]
    rock, soft = groups["chart_rock"]["cells"], groups["chart_soft"]["cells"]
    missed = rock - lowest["chart_rock"]
    numbers = (
        f"{compared}. At {lowest['above_m']:.2f} m, {_share(missed, rock)} of the cells the "
        f"chart marks as rock read as smooth, and {_share(lowest['chart_soft'], soft)} of the "
        "cells with a sample of sand or mud read as rough. The labels are part of that: a "
        "cell is marked rock if a charted rock area touches any corner of it, and a sample "
        "speaks for one point of its hectare."
    )
    if missed > 0.1 * rock or lowest["chart_soft"] > 0.05 * soft:
        return (
            f"{numbers} Rough ground is a hint that a cell holds reef, not a measurement of "
            "what the bottom is made of, and these numbers do not support overruling a "
            "chart or a sample with it. They do support a fourth source placed below the "
            "three there are: one that classes water they leave as soft sediment or "
            "unmapped, as a class of its own (rough ground, likely reef) and not as rock, "
            "with a line that rises with depth as the table above shows the floor doing. "
            "Until the habitat index has been tested with and without it, it stays out."
        )
    return (
        f"{numbers} On these numbers it could stand as a fourth source of bottom type, "
        "below the chart and its samples. It stays out until the habitat index has been "
        "tested with and without it."
    )


def _agreement(agree: dict) -> str:
    if "correlation" not in agree:
        return "The two surveys share too little water to compare their shading."
    return (
        f"Where both surveys measured the same seabed ({agree['cells']:,} squares of "
        f"{agree['cell_m']} m), the LiDAR's shade averaged to {agree['cell_m']} m and the "
        f"multibeam's own have a correlation of {agree['correlation']:.2f}. The surveys were "
        "made about twenty years apart and by different means, so shapes that both show "
        "are the seabed's and not one survey's artefacts."
    )


def rough_ground_markdown(facts: dict) -> str:
    """The last section of the report, written by scripts/build_relief.py."""
    rough = facts["rough_ground"]
    groups = rough["groups"]
    labels = (
        ("chart_rock", "Chart: marked as rock"),
        ("chart_soft", "Chart: a sample of sand or mud"),
        ("habitat_rock", "Habitat map: rock"),
        ("habitat_soft", "Habitat map: sand, mud or soft sediment"),
    )
    score = lambda value: "none to test" if value is None else f"{value:.3f}"  # noqa: E731
    parts = [
        ROUGH_GROUND_HEADING,
        "",
        "Written by `scripts/build_relief.py`; do not edit by hand. It describes "
        "`web/public/seabed/fine_roughness.bin.gz`. The method is in [seabed.md](seabed.md).",
        "",
        f"The layer has a value for {rough['cells']:,} cells: those whose depth is the "
        "LiDAR's. Each is the third roughest of the cell's hundred 10 m squares, and a "
        "square's roughness is the spread of the 2 m LiDAR depths in it about their "
        "best-fit plane, in metres. It is published and shown; nothing else is built from "
        "it.",
        "",
        "The relief tiles from the same build shade "
        f"{facts['shaded_km2']['lidar']:,} km² from the LiDAR and "
        f"{facts['shaded_km2']['multibeam']:,} km² from the multibeam. "
        + _agreement(facts["surveys_agree"]),
        "",
        "### By what the maps say the bottom is",
        "",
        "Neither map is the truth. The chart marks a cell as rock if a charted rock area "
        "touches it or a charted rock stands in it; a seabed sample is one point in the "
        "hectare. The habitat map was drawn at a coarse scale.",
        "",
        _table(
            [
                "Cells",
                "Count",
                "Lowest tenth (m)",
                "Quarter",
                "Median",
                "Three quarters",
                "Highest tenth",
            ],
            [_spread_row(label, groups[key]) for key, label in labels]
            + [_spread_row("Every cell with a value", rough["everywhere"])],
        ),
        "",
        "### How well it separates them",
        "",
        "The chance that a rock cell scores higher than a soft one (the area under the ROC "
        "curve): 1 is perfect, 0.5 is a coin. The first column is charted rock against "
        "charted samples of sand or mud; the second is the habitat map's rock against its "
        "soft sediment. Other ways of summarising the same 10 m squares, and the two "
        "terrain layers the 100 m grid already has, are scored on the same cells. With "
        f"this few labelled cells, differences under about {AUC_TIE:.2f} mean nothing.",
        "",
        _table(
            ["Scored by", "Chart labels", "Habitat map labels"],
            [[row["measure"], score(row["chart"]), score(row["habitat"])] for row in rough["auc"]],
        ),
        "",
        "### If a line were drawn",
        "",
        "Cells rougher than each value, of those the maps class each way.",
        "",
        _table(
            [
                "Rougher than (m)",
                "Of chart rock",
                "Of chart sand or mud",
                "Of habitat map rock",
                "Of habitat map soft sediment",
            ],
            [
                [
                    f"{row['above_m']:.2f}",
                    *(_share(row[key], groups[key]["cells"]) for key, _ in labels),
                ]
                for row in rough["thresholds"]
            ],
        ),
        "",
        "The last column is the rough ground the habitat map calls soft: either reef it "
        "misses, or sand waves, channel edges and survey noise.",
        "",
        "### The floor rises with depth",
        "",
        "Cells not classed as rock, by depth. The LiDAR's returns are noisier in deeper "
        "water, so the same flat sand scores higher there, and one line for all depths "
        "would be too strict inshore or too loose offshore.",
        "",
        _table(
            ["Depth (m)", "Cells", "Median (m)", "Highest tenth (m)"],
            [
                [
                    f"{row['from_m']} to {row['to_m']}",
                    f"{row['cells']:,}",
                    f"{row['median_m']:.2f}" if row["cells"] else "",
                    f"{row['p90_m']:.2f}" if row["cells"] else "",
                ]
                for row in rough["floor_by_depth"]
            ],
        ),
        "",
        "### As a source of bottom type",
        "",
        _verdict(rough),
        "",
    ]
    return "\n".join(parts)
