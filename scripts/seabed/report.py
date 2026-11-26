"""Check a build against the charted soundings and write the result down.

A charted sounding is one measured depth at a point; a grid cell is the mean over a
hectare. Charts also favour the shallowest sounding in a patch (it is the one that
matters to a keel), so on uneven ground a cell is expected to read a little deeper than
the soundings in it. Agreement within a metre or so on flat ground is as good as this
comparison gets.
"""

from __future__ import annotations

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
