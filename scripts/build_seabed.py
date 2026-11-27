#!/usr/bin/env python3
"""Build the seabed grids the site shows: depth, where each depth came from, slope,
roughness and bottom type, on a 100 m grid of Bream Bay.

Run by hand from the repo root, on a development machine:

    export LINZ_API_KEY=...            # LINZ Data Service key; never commit it
    uv run python scripts/build_seabed.py

It downloads each source once into data/seabed/raw/ (not committed), then writes

    web/public/seabed/manifest.json    grid, scaling, legends, sources and licences
    web/public/seabed/*.bin.gz         one byte grid per layer, and the 20 m drawing grid
    web/public/seabed/contours.geojson depth contours
    docs/seabed-report.md              what went into this build, and how it checks out

Review the diff and commit those. The method is described in docs/seabed.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seabed import (  # noqa: E402
    bottom,
    depth,
    distance,
    drawing,
    grid,
    publish,
    report,
    sources,
)

ROOT = Path(__file__).resolve().parent.parent
CONTOUR_LEVELS_M = (2, 5, 10, 20, 30, 40, 50, 75, 100)
# A contour keeps the vertices that move it by more than this, and is dropped if it is
# shorter than this: a ring that small is one bump or one patch of survey noise.
CONTOUR_TOLERANCE_M = 5.0
CONTOUR_MIN_LENGTH_M = 300.0

# LiDAR is trusted to this depth below chart datum; anything deeper is dropped and the
# next source is used. Airborne LiDAR loses the bottom gradually as the water deepens,
# and the last few metres it reports are the least sure. Down to 40 m it agrees with the
# charted soundings as well as it does in the shallows (docs/seabed-report.md); beyond
# 40 m no sounding falls inside its cover, so nothing there could be checked.
LIDAR_MAX_DEPTH_M = 40.0


# --- Inputs -----------------------------------------------------------------------------


@dataclass
class ChartBand:
    """One scale band of LINZ chart layers, as GeoJSON features in NZTM."""

    name: str
    soundings: list = field(default_factory=list)
    contours: list = field(default_factory=list)
    depth_areas: list = field(default_factory=list)
    land: list = field(default_factory=list)
    quality: list = field(default_factory=list)
    seabed_polygons: list = field(default_factory=list)
    seabed_points: list = field(default_factory=list)
    rocks: list = field(default_factory=list)


@dataclass
class Inputs:
    lidar_fine: np.ndarray  # NZVD2016 heights on the nested 10 m grid, NaN = no data
    multibeam_fine: np.ndarray  # model heights on the nested 20 m grid, NaN = no data
    bands: list[ChartBand]  # finest scale first
    habitat: list  # DOC habitat polygons, GeoJSON features in NZTM
    gebco: np.ndarray  # (rows, cols, 3): easting, northing, height above mean sea level


def to_lonlat(easting, northing):
    from rasterio.warp import transform

    lon, lat = transform(grid.CRS, "EPSG:4326", list(np.ravel(easting)), list(np.ravel(northing)))
    return np.array(lon), np.array(lat)


def lonlat_bounds() -> tuple[float, float, float, float]:
    from rasterio.warp import transform_bounds

    return transform_bounds(
        grid.CRS, "EPSG:4326", grid.WEST_E, grid.SOUTH_N, grid.EAST_E, grid.NORTH_N, densify_pts=101
    )


def load_inputs(raw: Path) -> Inputs:
    print("LiDAR tiles ...")
    lidar = sources.mosaic(sources.lidar_paths(raw), sources.LIDAR_RES_M)
    print("multibeam model ...")
    multibeam = sources.warp_to_fine(sources.multibeam_path(raw), sources.MULTIBEAM_RES_M)
    bands = []
    for spec in sources.CHART_BANDS:
        print(f"chart layers, {spec['name']} ...")
        layers = {k: sources.wfs_features(raw, v) for k, v in spec.items() if k != "name"}
        bands.append(ChartBand(name=spec["name"], **layers))
    print("DOC habitat map ...")
    habitat = sources.doc_habitat_features(raw)
    print("GEBCO background ...")
    gebco = sources.gebco_heights(raw, to_lonlat)
    return Inputs(lidar, multibeam, bands, habitat, gebco)


# --- Chart layers to grids ----------------------------------------------------------------


def rasterize(shapes, fill, dtype, all_touched=False, cell_m=grid.CELL_M) -> np.ndarray:
    """Burn (geometry, value) pairs onto the grid, or onto a finer grid nested in it.
    By default a cell takes the polygon its centre is in; all_touched marks every cell
    a shape reaches."""
    from rasterio.features import rasterize as burn
    from rasterio.transform import from_origin

    shape = grid.fine_shape(cell_m)
    shapes = [(geometry, value) for geometry, value in shapes if geometry]
    if not shapes:
        return np.full(shape, fill, dtype=dtype)
    return burn(
        shapes,
        out_shape=shape,
        transform=from_origin(grid.WEST_E, grid.NORTH_N, cell_m, cell_m),
        fill=fill,
        dtype=dtype,
        all_touched=all_touched,
    )


def number(value) -> float:
    """A chart attribute as a float; blank or missing is NaN."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def point_coordinates(geometry) -> list:
    if geometry["type"] == "Point":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiPoint":
        return list(geometry["coordinates"])
    return []


def line_vertices(geometry) -> list:
    kind, coords = geometry["type"], geometry["coordinates"]
    if kind == "LineString":
        return list(coords)
    if kind in ("MultiLineString", "Polygon"):
        return [xy for part in coords for xy in part]
    if kind == "MultiPolygon":
        return [xy for polygon in coords for ring in polygon for xy in ring]
    return []


def survey_year(feature) -> int:
    """Year a chart "quality of data" area's survey finished, 0 if not recorded."""
    props = feature["properties"]
    for key in ("surend", "sursta"):
        text = str(props.get(key) or "")
        if len(text) >= 4 and text[:4].isdigit():
            return int(text[:4])
    return 0


@dataclass
class Chart:
    """The chart layers of all bands, reduced to what the build needs."""

    easting: np.ndarray  # depth points for the surface: soundings, contour vertices
    northing: np.ndarray
    value: np.ndarray
    soundings: np.ndarray  # (n, 3) easting, northing, depth: the soundings alone
    land: np.ndarray  # bool grid: charted land
    shallowest: np.ndarray  # charted depth band of each cell, NaN where none
    deepest: np.ndarray
    year: np.ndarray  # year the survey behind each cell finished, 0 = not recorded
    rock: np.ndarray  # bottom class grids from the chart: rock areas and rock marks
    rock_marks: np.ndarray  # the charted rocks that are marks at a point, alone
    samples: np.ndarray


def read_chart(bands: list[ChartBand]) -> Chart:
    """Reduce the chart bands to points and grids, the finest band winning where bands overlap.

    A coarser chart is a generalisation of the finer one, with contours moved for
    legibility, so its features are used only in cells no finer band covers.
    """
    covered = np.zeros(grid.SHAPE, dtype=bool)  # by a finer band already
    land = np.zeros(grid.SHAPE, dtype=bool)
    shallowest = np.full(grid.SHAPE, np.nan)
    deepest = np.full(grid.SHAPE, np.nan)
    year = np.zeros(grid.SHAPE, dtype=np.int32)
    rock = np.full(grid.SHAPE, bottom.UNKNOWN, dtype=np.uint8)
    rock_marks = np.full(grid.SHAPE, bottom.UNKNOWN, dtype=np.uint8)
    samples = np.full(grid.SHAPE, bottom.UNKNOWN, dtype=np.uint8)
    points, soundings = [], []

    def usable(xy) -> bool:
        row, col = grid.cell_of(xy[0], xy[1])
        return not grid.inside(row, col) or not covered[row, col]

    for band in bands:
        band_land = rasterize([(f["geometry"], 1) for f in band.land], 0, "uint8").astype(bool)
        areas = [f for f in band.depth_areas if not np.isnan(number(f["properties"].get("drval1")))]
        # Deepest bands are burnt first so that where polygons overlap the shallower wins.
        areas.sort(key=lambda f: -number(f["properties"]["drval1"]))
        low = rasterize(
            [(f["geometry"], number(f["properties"]["drval1"])) for f in areas], np.nan, "float32"
        )
        high = rasterize(
            [(f["geometry"], number(f["properties"].get("drval2"))) for f in areas],
            np.nan,
            "float32",
        )
        dated = sorted(band.quality, key=survey_year)  # newest burnt last, so it wins
        band_year = rasterize([(f["geometry"], survey_year(f)) for f in dated], 0, "int32")
        here = (band_land | ~np.isnan(low)) & ~covered

        for feature in band.soundings:
            value = number(feature["properties"].get("depth"))
            for xy in point_coordinates(feature["geometry"]):
                z = value if not np.isnan(value) else (xy[2] if len(xy) > 2 else np.nan)
                if not np.isnan(z) and usable(xy):
                    points.append((xy[0], xy[1], z))
                    soundings.append((xy[0], xy[1], z))
        for feature in band.contours:
            value = number(feature["properties"].get("valdco"))
            if np.isnan(value):
                continue
            points += [
                (xy[0], xy[1], value) for xy in line_vertices(feature["geometry"]) if usable(xy)
            ]
        # The charted coastline is mean high water springs: it anchors the surface at the shore.
        for feature in band.land:
            points += [
                (xy[0], xy[1], -depth.MHWS_M)
                for xy in line_vertices(feature["geometry"])
                if usable(xy)
            ]

        land |= band_land & here
        shallowest = np.where(here, low, shallowest)
        deepest = np.where(here, high, deepest)
        year = np.where(here, band_year, year)

        rock_polygons = [
            (f["geometry"], bottom.ROCK)
            for f in band.seabed_polygons
            if bottom.class_of_natsur(f["properties"].get("natsur")) == bottom.ROCK
        ]
        rock_here = rasterize(rock_polygons, bottom.UNKNOWN, "uint8", all_touched=True)
        rock_xy = np.array(
            [xy[:2] for f in band.rocks for xy in point_coordinates(f["geometry"])]
        ).reshape(-1, 2)
        rock_points = bottom.points_to_cells(
            rock_xy[:, 0], rock_xy[:, 1], np.full(len(rock_xy), bottom.ROCK)
        )
        rock = np.where((rock == bottom.UNKNOWN) & here, np.maximum(rock_here, rock_points), rock)
        rock_marks = np.where((rock_marks == bottom.UNKNOWN) & here, rock_points, rock_marks)
        sample_xy, sample_class = [], []
        for feature in band.seabed_points:
            for xy in point_coordinates(feature["geometry"]):
                sample_xy.append(xy[:2])
                sample_class.append(bottom.class_of_natsur(feature["properties"].get("natsur")))
        sample_xy = np.array(sample_xy).reshape(-1, 2)
        sampled = bottom.points_to_cells(sample_xy[:, 0], sample_xy[:, 1], np.array(sample_class))
        samples = np.where((samples == bottom.UNKNOWN) & here, sampled, samples)

        covered |= here

    xyz = np.array(points, dtype=float).reshape(-1, 3)
    return Chart(
        xyz[:, 0],
        xyz[:, 1],
        xyz[:, 2],
        np.array(soundings).reshape(-1, 3),
        land,
        shallowest,
        deepest,
        year,
        rock,
        rock_marks,
        samples,
    )


@dataclass
class FineChart:
    """What the drawing grid takes straight from the chart, on cells of drawing.CELL_M."""

    land: np.ndarray  # bool: charted land
    covered: np.ndarray  # bool: the chart says something here
    shallowest: np.ndarray  # charted depth band, NaN where none
    deepest: np.ndarray
    rock: np.ndarray  # bottom class: the seabed areas charted as rock


def read_chart_fine(bands: list[ChartBand]) -> FineChart:
    """The chart's coastline and depth bands at the scale the map is drawn at.

    As in read_chart, the finest band that covers a spot decides.
    """
    cell_m = drawing.CELL_M
    land = np.zeros(drawing.SHAPE, dtype=bool)
    covered = np.zeros(drawing.SHAPE, dtype=bool)
    shallowest = np.full(drawing.SHAPE, np.nan, dtype=np.float32)
    deepest = np.full(drawing.SHAPE, np.nan, dtype=np.float32)
    rock = np.full(drawing.SHAPE, bottom.UNKNOWN, dtype=np.uint8)
    for band in bands:
        band_land = rasterize(
            [(f["geometry"], 1) for f in band.land], 0, "uint8", cell_m=cell_m
        ).astype(bool)
        band_rock = rasterize(
            [
                (f["geometry"], bottom.ROCK)
                for f in band.seabed_polygons
                if bottom.class_of_natsur(f["properties"].get("natsur")) == bottom.ROCK
            ],
            bottom.UNKNOWN,
            "uint8",
            all_touched=True,
            cell_m=cell_m,
        )
        areas = [f for f in band.depth_areas if not np.isnan(number(f["properties"].get("drval1")))]
        areas.sort(key=lambda f: -number(f["properties"]["drval1"]))
        low = rasterize(
            [(f["geometry"], number(f["properties"]["drval1"])) for f in areas],
            np.nan,
            "float32",
            cell_m=cell_m,
        )
        high = rasterize(
            [(f["geometry"], number(f["properties"].get("drval2"))) for f in areas],
            np.nan,
            "float32",
            cell_m=cell_m,
        )
        here = (band_land | ~np.isnan(low)) & ~covered
        land |= band_land & here
        shallowest = np.where(here, low, shallowest)
        deepest = np.where(here, high, deepest)
        rock = np.where(here, band_rock, rock)
        covered |= here
    return FineChart(land, covered, shallowest, deepest, rock)


def edge_cells(values: np.ndarray):
    """Cells of a higher-trust surface that touch a cell it does not cover, as points.

    Fed to the chart surface so it meets LiDAR and multibeam at their edges instead of
    leaving a step there.
    """
    have = ~np.isnan(values)
    padded = np.pad(have, 1, constant_values=True)
    surrounded = padded[:-2, 1:-1] & padded[2:, 1:-1] & padded[1:-1, :-2] & padded[1:-1, 2:]
    rows, cols = np.nonzero(have & ~surrounded)
    easting, northing = grid.cell_centre(rows, cols)
    return easting, northing, values[rows, cols]


# --- The build ----------------------------------------------------------------------------


@dataclass
class Grids:
    depth: np.ndarray
    source: np.ndarray
    slope: np.ndarray
    roughness: np.ndarray
    bottom: np.ndarray
    bottom_source: np.ndarray
    reef_distance: np.ndarray  # metres to the nearest reef cell
    shore_distance: np.ndarray  # metres to the mainland shore
    # The same merges on the 20 m grid, for drawing only (seabed/drawing.py).
    drawing_depth: np.ndarray
    drawing_source: np.ndarray
    drawing_bottom: np.ndarray
    drawing_bottom_source: np.ndarray


def build(inputs: Inputs) -> tuple[Grids, dict]:
    """Everything between the raw sources and the published arrays. No network, no files."""
    facts: dict = {}

    # 1. The two surveyed surfaces, each on its own fine grid.
    lidar_fine = depth.depth_from_nzvd2016(inputs.lidar_fine)
    lidar_all, lidar_land = depth.sea_cells(lidar_fine)
    multibeam_fine = depth.depth_from_multibeam(inputs.multibeam_fine)
    multibeam, _ = depth.sea_cells(multibeam_fine)

    # 2. The chart: land, depth bands, survey dates, and the points for its surface.
    #    The LiDAR is checked against the soundings before its depth limit is applied,
    #    so the report shows what the limit is protecting against.
    chart = read_chart(inputs.bands)
    facts["lidar_check"] = report.compare(lidar_all, chart.soundings, report.DEPTH_BANDS_M)
    facts["lidar_check_by_survey"] = report.compare_at_points(
        np.where(depth.is_sea(lidar_fine), lidar_fine, np.nan),
        sources.LIDAR_RES_M,
        chart.soundings,
        chart.year,
    )
    facts["multibeam_check"] = report.compare(multibeam, chart.soundings, report.DEPTH_BANDS_M)
    facts["lidar_multibeam_overlap"] = report.overlap(lidar_all, multibeam)
    with np.errstate(invalid="ignore"):
        lidar_fine = np.where(lidar_fine > LIDAR_MAX_DEPTH_M, np.nan, lidar_fine)
    lidar, _ = depth.sea_cells(lidar_fine)
    facts["lidar_cells_dropped_as_too_deep"] = int((~np.isnan(lidar_all) & np.isnan(lidar)).sum())

    # 3. One surface through the charted soundings and contours, tied to the surveyed
    #    surfaces where it meets them and kept inside the charted depth bands.
    surveyed = np.where(np.isnan(lidar), multibeam, lidar)
    edge_e, edge_n, edge_z = edge_cells(surveyed)
    e, n, z = depth.thin(
        np.concatenate([chart.easting, edge_e]),
        np.concatenate([chart.northing, edge_n]),
        np.concatenate([chart.value, edge_z]),
    )
    charted = depth.interpolate(e, n, z)
    charted = depth.clamp_to_depth_areas(charted, chart.shallowest, chart.deepest)
    # Last, so that a sounding on a shoal smaller than a cell is not clamped away.
    charted = depth.honour_soundings(charted, chart.soundings)
    facts["chart_points"] = int(len(z))

    # 4. The global grid, for water no chart covers.
    background = depth.interpolate(
        inputs.gebco[..., 0].ravel(),
        inputs.gebco[..., 1].ravel(),
        depth.depth_from_msl(inputs.gebco[..., 2].ravel()),
    )
    background = np.where(depth.is_sea(background), background, np.nan)

    # 5. Merge in order of trust. Land is what the LiDAR saw as land or, where the
    #    LiDAR saw nothing, what the chart draws as land.
    by_chart = depth.chart_source(chart.year)
    layers = [(depth.LIDAR, lidar), (depth.MULTIBEAM, multibeam)]
    layers += [
        (src, np.where(by_chart == src.code, charted, np.nan))
        for src in (depth.CHART_RECENT, depth.CHART_OLD, depth.CHART_UNDATED)
    ]
    layers.append((depth.BACKGROUND, background))
    merged, source = depth.merge(layers)
    land = (lidar_land >= 0.5) | (chart.land & np.isnan(surveyed))
    merged[land] = np.nan
    source[land] = 0

    # 6. Slope and roughness, each from one source's own fine grid.
    slope = np.full(grid.SHAPE, np.nan)
    rough = np.full(grid.SHAPE, np.nan)
    for src, fine, res in (
        (depth.LIDAR, lidar_fine, sources.LIDAR_RES_M),
        (depth.MULTIBEAM, multibeam_fine, sources.MULTIBEAM_RES_M),
    ):
        mine = source == src.code
        s, r = depth.cell_terrain(fine, res, mine)
        slope = np.where(mine, s, slope)
        rough = np.where(mine, r, rough)

    # 7. Bottom type.
    habitat_shapes = [
        (f["geometry"], bottom.class_of_substrate(f["properties"].get("Substrate")))
        for f in inputs.habitat
    ]
    habitat = rasterize(habitat_shapes, bottom.UNKNOWN, "uint8")
    kind, kind_source = bottom.merge(
        [
            (bottom.CHART_ROCK, chart.rock),
            (bottom.CHART_SAMPLE, chart.samples),
            (bottom.HABITAT_MAP, habitat),
        ]
    )
    sea = source != 0
    kind = np.where(sea, kind, bottom.UNKNOWN).astype(np.uint8)
    kind_source = np.where(sea, kind_source, bottom.NO_SOURCE).astype(np.uint8)

    # 8. The same merge on a 20 m grid, for the map to draw when zoomed in.
    #    Charted water is the same surface through the same points, read at 20 m (or,
    #    beyond the outermost point, the 100 m grid drawn smoothly), and held inside the
    #    depth bands as the chart draws them at that scale.
    fine_chart = read_chart_fine(inputs.bands)
    charted_fine = depth.interpolate(e, n, z, at=drawing.centres())
    charted_fine = np.where(np.isnan(charted_fine), drawing.between_centres(merged), charted_fine)
    charted_fine = depth.clamp_to_depth_areas(
        charted_fine, fine_chart.shallowest, fine_chart.deepest
    )
    drawn, drawn_source = drawing.surface(
        lidar_fine,
        multibeam_fine,
        charted_fine,
        source,
        fine_chart.land,
        fine_chart.covered,
    )
    drawn_kind, drawn_kind_source = drawing.bottom_type(
        fine_chart.rock,
        chart.rock_marks,
        chart.samples,
        rasterize(habitat_shapes, bottom.UNKNOWN, "uint8", cell_m=drawing.CELL_M),
        drawn_source,
    )

    grids = Grids(
        merged,
        source,
        slope,
        rough,
        kind,
        kind_source,
        distance.to_reef(kind, sea),
        distance.to_mainland(sea),
        drawn,
        drawn_source,
        drawn_kind,
        drawn_kind_source,
    )
    facts["final_check"] = report.compare(merged, chart.soundings, report.DEPTH_BANDS_M)
    facts["spot_checks"] = report.spot_checks(merged, source, chart.soundings, to_lonlat)
    facts["cells"] = report.cell_counts(grids)
    return grids, facts


# --- Writing ------------------------------------------------------------------------------

LICENCE_LINZ = "CC BY 4.0, Toitū Te Whenua Land Information New Zealand"

SOURCE_NOTES = {
    "lidar": {
        "name": "LINZ coastal LiDAR, Whangārei to Bream Bay and Mangawhai to Snells (2025), 10 m",
        "url": "https://registry.opendata.aws/nz-coastal/",
        "licence": LICENCE_LINZ,
    },
    "multibeam": {
        "name": "LINZ Shipping Lane 1 Multibeam 20m Depth Model (surveys HS6 and HS15)",
        "url": "https://data.linz.govt.nz/layer/116628",
        "licence": LICENCE_LINZ,
    },
    "chart": {
        "name": "LINZ nautical chart data (soundings, depth contours, depth areas, "
        "quality of data), three scale bands",
        "url": "https://data.linz.govt.nz/layer/50866",
        "licence": LICENCE_LINZ,
    },
    "background": {
        "name": "GEBCO 2020 grid, through Open Topo Data",
        "url": "https://www.gebco.net/",
        "licence": "Public domain, GEBCO Compilation Group (2020)",
    },
    "habitat_map": {
        "name": "Kerr, V.C. 2010. Marine Habitat Map of Northland: Mangawhai to Ahipara, "
        "version 1. Department of Conservation",
        "url": "https://www.doc.govt.nz/documents/conservation/marine-and-coastal/"
        "northland-marine-habitat-map-report-1.pdf",
        "licence": "Not stated on the map service; attributed to the Department of Conservation",
    },
}


def manifest(grids: Grids, facts: dict, contour_levels) -> dict:
    counts = facts["cells"]
    check_lon, check_lat = to_lonlat(*CHECK_POINTS.T)
    chart_note = SOURCE_NOTES["chart"]
    note_of = {
        depth.LIDAR.key: SOURCE_NOTES["lidar"],
        depth.MULTIBEAM.key: SOURCE_NOTES["multibeam"],
        depth.BACKGROUND.key: SOURCE_NOTES["background"],
    }
    return {
        "schema": 2,
        "built": dt.date.today().isoformat(),
        "grid": {
            "crs": grid.CRS,
            "cell_m": grid.CELL_M,
            "west_e": grid.WEST_E,
            "north_n": grid.NORTH_N,
            "ncols": grid.NCOLS,
            "nrows": grid.NROWS,
            "order": "rows from north to south, cells from west to east",
        },
        # West, south, east, north: the latitude and longitude box the grid fits in.
        "bounds": [round(v, 6) for v in lonlat_bounds()],
        # For the browser to check its own NZTM arithmetic against PROJ before it trusts
        # a tap: [longitude, latitude, easting, northing].
        "projection_check": [
            [round(float(lon), 7), round(float(lat), 7), float(e), float(n)]
            for lon, lat, (e, n) in zip(check_lon, check_lat, CHECK_POINTS, strict=True)
        ],
        "datum": {
            "name": "Chart datum, Marsden Point",
            "note": "Depths are metres below chart datum, the zero of the tide predictions. "
            "Negative depths dry at low tide.",
            "chart_datum_in_nzvd2016_m": round(depth.CD_NZVD2016_M, 3),
            "mhws_m": depth.MHWS_M,
            "msl_m": depth.MSL_M,
        },
        "layers": {
            "depth": publish.scaled_layer(
                publish.DEPTH, file="depth.bin.gz", unit="m", label="Depth below chart datum"
            ),
            "depth_source": {
                "file": "depth_source.bin.gz",
                "dtype": "uint8",
                "label": "Where the depth comes from",
                "classes": [
                    {
                        "code": src.code,
                        "key": src.key,
                        "label": src.label,
                        "quality": src.quality,
                        "cells": counts["source"].get(src.key, 0),
                        **note_of.get(src.key, chart_note),
                    }
                    for src in depth.SOURCES
                ],
            },
            "slope": publish.scaled_layer(
                publish.SLOPE,
                file="slope.bin.gz",
                unit="degrees",
                label="Slope",
                note="Mean slope of the cell, measured on the 10 m LiDAR or 20 m multibeam "
                "grid. Empty where the depth is from charts.",
            ),
            "roughness": publish.scaled_layer(
                publish.ROUGHNESS,
                file="roughness.bin.gz",
                unit="m",
                label="Roughness",
                note="Standard deviation of depth within the cell about its best-fit plane, "
                "from the same fine grids as slope.",
            ),
            "bottom": {
                "file": "bottom.bin.gz",
                "dtype": "uint8",
                "label": "Bottom type",
                "classes": [
                    {**cls, "cells": counts["bottom"].get(cls["key"], 0)} for cls in bottom.CLASSES
                ],
            },
            "reef_distance": publish.scaled_layer(
                publish.REEF_DISTANCE,
                file="reef_distance.bin.gz",
                unit="m",
                label="Distance to the nearest reef",
                note="From the centre of the cell to the centre of the nearest cell of reef "
                "or rock; 0 on reef. Stops at 6,350 m.",
            ),
            "shore_distance": publish.scaled_layer(
                publish.SHORE_DISTANCE,
                file="shore_distance.bin.gz",
                unit="m",
                label="Distance to the mainland shore",
                note="To the nearest cell of land that is not an island. Stops at 12,700 m.",
            ),
            "bottom_source": {
                "file": "bottom_source.bin.gz",
                "dtype": "uint8",
                "label": "Where the bottom type comes from",
                "classes": [
                    {
                        **src,
                        **(
                            SOURCE_NOTES["habitat_map"]
                            if src["code"] == bottom.HABITAT_MAP
                            else chart_note
                            if src["code"] != bottom.NO_SOURCE
                            else {}
                        ),
                    }
                    for src in bottom.SOURCES
                ],
            },
        },
        "quality": [
            {"code": code, **entry, "cells": counts["quality"].get(entry["key"], 0)}
            for code, entry in enumerate(depth.QUALITY)
        ],
        # For drawing only: the same merge on a finer grid. Nothing is computed from it.
        "drawing": {
            "cell_m": drawing.CELL_M,
            "ncols": drawing.SHAPE[1],
            "nrows": drawing.SHAPE[0],
            "note": "Depth: LiDAR and multibeam at 20 m where they exist; elsewhere the "
            "surface through the charted soundings and contours, read at 20 m; lightly "
            "smoothed. Bottom type: charted rock and the habitat map as their outlines run.",
            "depth": {
                **publish.scaled_layer(publish.DEPTH, file="drawing_depth.bin.gz", unit="m"),
                "predictor": publish.PREDICTOR,
            },
            # A depth_source code, plus past_shore on the fringe carried onto the land
            # for the map's own coastline to trim.
            "source": {
                "file": "drawing_source.bin.gz",
                "dtype": "uint8",
                "past_shore": drawing.PAST_SHORE,
            },
            # Codes as in layers.bottom and layers.bottom_source.
            "bottom": {"file": "drawing_bottom.bin.gz", "dtype": "uint8"},
            "bottom_source": {"file": "drawing_bottom_source.bin.gz", "dtype": "uint8"},
        },
        "contours": {
            "file": "contours.geojson",
            "levels_m": list(contour_levels),
            "note": "Drawn from the 20 m drawing grid. Not for navigation.",
        },
    }


# Five points spread over the grid, in NZTM, for the browser's projection self-check.
CHECK_POINTS = np.array(
    [
        [grid.WEST_E, grid.NORTH_N],
        [grid.EAST_E, grid.NORTH_N],
        [grid.WEST_E, grid.SOUTH_N],
        [grid.EAST_E, grid.SOUTH_N],
        [(grid.WEST_E + grid.EAST_E) / 2, (grid.SOUTH_N + grid.NORTH_N) / 2],
    ],
    dtype=float,
)


def write(grids: Grids, facts: dict, out: Path, report_path: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "depth.bin.gz": publish.encode(grids.depth, publish.DEPTH),
        "depth_source.bin.gz": grids.source,
        "slope.bin.gz": publish.encode(grids.slope, publish.SLOPE),
        "roughness.bin.gz": publish.encode(grids.roughness, publish.ROUGHNESS),
        "bottom.bin.gz": grids.bottom,
        "bottom_source.bin.gz": grids.bottom_source,
        "reef_distance.bin.gz": publish.encode(grids.reef_distance, publish.REEF_DISTANCE),
        "shore_distance.bin.gz": publish.encode(grids.shore_distance, publish.SHORE_DISTANCE),
    }
    for name, stored in files.items():
        (out / name).write_bytes(publish.to_bytes(stored))
    (out / "drawing_depth.bin.gz").write_bytes(
        publish.to_bytes_predicted(
            publish.encode(grids.drawing_depth, publish.DEPTH), drawing.SHAPE
        )
    )
    for name, stored in (
        ("drawing_source.bin.gz", grids.drawing_source),
        ("drawing_bottom.bin.gz", grids.drawing_bottom),
        ("drawing_bottom_source.bin.gz", grids.drawing_bottom_source),
    ):
        (out / name).write_bytes(publish.to_bytes(stored, drawing.SHAPE))
    # The lines are drawn from the surface the map paints, so they sit on its colour steps.
    in_water = (grids.drawing_source != 0) & (grids.drawing_source < drawing.PAST_SHORE)
    lines = publish.contours(
        np.where(in_water, grids.drawing_depth, np.nan),
        CONTOUR_LEVELS_M,
        to_lonlat,
        tolerance_m=CONTOUR_TOLERANCE_M,
        min_length_m=CONTOUR_MIN_LENGTH_M,
        sigma_cells=0,
    )
    (out / "contours.geojson").write_text(json.dumps(lines, separators=(",", ":")) + "\n")
    # scripts/build_relief.py adds a layer and a key to the manifest and a section to the
    # report. They are kept here, and are out of date until that script is run again.
    described = manifest(grids, facts, CONTOUR_LEVELS_M)
    manifest_path = out / "manifest.json"
    if manifest_path.exists():
        before = json.loads(manifest_path.read_text())
        if "relief" in before:
            described["relief"] = before["relief"]
        if "fine_roughness" in before.get("layers", {}):
            described["layers"]["fine_roughness"] = before["layers"]["fine_roughness"]
    publish.write_json(manifest_path, described)
    rough_ground = report.rough_ground_section(
        report_path.read_text() if report_path.exists() else ""
    )
    report_path.write_text(report.joined(report.markdown(facts, LIDAR_MAX_DEPTH_M), rough_ground))
    size = sum(path.stat().st_size for path in out.iterdir())
    print(f"wrote {len(files) + 6} files to {out} ({size / 1024:.0f} kB) and {report_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--raw", type=Path, default=ROOT / "data" / "seabed" / "raw")
    parser.add_argument("--out", type=Path, default=ROOT / "web" / "public" / "seabed")
    parser.add_argument("--report", type=Path, default=ROOT / "docs" / "seabed-report.md")
    args = parser.parse_args()
    try:
        inputs = load_inputs(args.raw)
    except sources.MissingKey as error:
        print(f"Stopped: {error}", file=sys.stderr)
        return 2
    grids, facts = build(inputs)
    write(grids, facts, args.out, args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
