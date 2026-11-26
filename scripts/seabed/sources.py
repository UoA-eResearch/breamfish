"""Fetch each source once and keep it under data/seabed/raw/ (not committed).

A second run reads the cache and touches the network only for what is missing, so the
build can be repeated offline and gives the same answer. Delete a cached file to fetch
it again. Endpoints, layer numbers and what was verified are in docs/data-sources.md.

The LINZ Data Service key comes from the environment (LINZ_API_KEY) and is sent only
as a request header, so it never lands in a URL, a cache file name or an error message.
"""

from __future__ import annotations

import io
import json
import os
import time
import zipfile
from pathlib import Path

import httpx
import numpy as np

from seabed import grid

USER_AGENT = "breamfish-seabed-build (+https://github.com/UoA-eResearch/breamfish)"
TIMEOUT_S = 120

# A margin around the study box, so soundings just outside it still shape the surface
# at its edge.
MARGIN_DEG = 0.03
WEST, SOUTH = grid.BOX_WEST - MARGIN_DEG, grid.BOX_SOUTH - MARGIN_DEG
EAST, NORTH = grid.BOX_EAST + MARGIN_DEG, grid.BOX_NORTH + MARGIN_DEG

LIDAR_BUCKET = "https://nz-coastal.s3.ap-southeast-2.amazonaws.com"
# The two 2025 coastal surveys that meet in the box, and their 10 m tiles that touch it.
# Where both have a value the first listed is used.
LIDAR_TILES = (
    ("northland/whangarei-to-bream-bay_2025", ("AX30", "AX31", "AY31")),
    ("auckland/mangawhai-to-snells_2025", ("AY31", "AY32")),
)
LIDAR_RES_M = 10

LDS = "https://data.linz.govt.nz/services"
MULTIBEAM_LAYER = 116628  # Shipping Lane 1 Multibeam 20m Depth Model (1999)
MULTIBEAM_RES_M = 20
MULTIBEAM_CRS = (
    "EPSG:32760"  # the model's own: UTM zone 60S. Asked for as is, so LDS resamples nothing.
)

# LINZ chart layers come in scale bands. The finer band (harbour charts) is listed first
# and wins where both cover a cell.
CHART_BANDS = (
    {
        "name": "1:4k to 1:22k",
        "soundings": 50858,
        "contours": 50672,
        "depth_areas": 50671,
        "land": 50691,
        "quality": 50707,
        "seabed_polygons": 50734,
        "seabed_points": 50733,
        "rocks": 50755,
    },
    {
        "name": "1:22k to 1:90k",
        "soundings": 50866,
        "contours": 50554,
        "depth_areas": 50553,
        "land": 50569,
        "quality": 50584,
        "seabed_polygons": 50603,
        "seabed_points": 50602,
        "rocks": 50626,
    },
    {
        "name": "1:90k to 1:350k",
        "soundings": 50506,
        "contours": 50448,
        "depth_areas": 50447,
        "land": 50461,
        "quality": 50476,
        "seabed_polygons": 50496,
        "seabed_points": 50495,
        "rocks": 50513,
    },
)
SURVEY_INDEX_LAYER = 53388

DOC_HABITAT = (
    "https://seasketch.doc.govt.nz/arcgis/rest/services/National/"
    "NZMPASAG_Habitats_Northland_2009_201810/MapServer/0/query"
)
GEBCO = "https://api.opentopodata.org/v1/gebco2020"


class MissingKey(RuntimeError):
    pass


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=TIMEOUT_S, headers={"User-Agent": USER_AGENT}, follow_redirects=True
    )


def _lds_headers() -> dict:
    key = os.environ.get("LINZ_API_KEY", "").strip()
    if not key:
        raise MissingKey(
            "LINZ_API_KEY is not set. Export it in your shell (never commit it) and run again."
        )
    return {"Authorization": f"key {key}"}


def _cached_json(path: Path, fetch) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    payload = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    return payload


# --- LiDAR ------------------------------------------------------------------------------


def lidar_paths(raw: Path) -> list[Path]:
    """The 10 m LiDAR tiles, downloaded from the public bucket if not cached."""
    paths = []
    with _client() as client:
        for survey, tiles in LIDAR_TILES:
            for tile in tiles:
                path = raw / "lidar" / f"{survey.split('/')[1]}_{tile}.tiff"
                if not path.exists():
                    url = f"{LIDAR_BUCKET}/{survey}/dem_{LIDAR_RES_M}m/2193/{tile}.tiff"
                    response = client.get(url)
                    response.raise_for_status()
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(response.content)
                paths.append(path)
    return paths


def mosaic(paths: list[Path], res_m: int) -> np.ndarray:
    """Lay rasters that are already in NZTM at res_m on the nested fine grid (NaN = no data).

    Tiles must sit on the same res_m lattice as the grid; nothing is resampled. Where
    tiles overlap, the first one with a value is kept.
    """
    import rasterio

    rows, cols = grid.fine_shape(res_m)
    out = np.full((rows, cols), np.nan, dtype=np.float32)
    for path in paths:
        with rasterio.open(path) as src:
            t = src.transform
            if src.crs.to_epsg() != 2193 or (t.a, t.e) != (res_m, -res_m):
                raise ValueError(f"{path.name}: expected EPSG:2193 at {res_m} m")
            col0 = (t.c - grid.WEST_E) / res_m
            row0 = (grid.NORTH_N - t.f) / res_m
            if col0 != int(col0) or row0 != int(row0):
                raise ValueError(f"{path.name}: not on the grid's {res_m} m lattice")
            col0, row0 = int(col0), int(row0)
            # The part of the tile that falls inside the grid.
            r_lo, r_hi = max(0, row0), min(rows, row0 + src.height)
            c_lo, c_hi = max(0, col0), min(cols, col0 + src.width)
            if r_lo >= r_hi or c_lo >= c_hi:
                continue
            window = rasterio.windows.Window(c_lo - col0, r_lo - row0, c_hi - c_lo, r_hi - r_lo)
            tile = src.read(1, window=window).astype(np.float32)
            tile[tile == src.nodata] = np.nan
            target = out[r_lo:r_hi, c_lo:c_hi]
            np.copyto(target, tile, where=np.isnan(target))
    return out


# --- LINZ Data Service: vectors (WFS) -----------------------------------------------------


def wfs_features(raw: Path, layer: int) -> list[dict]:
    """Every feature of an LDS layer that touches the box, as GeoJSON in NZTM."""

    def fetch() -> dict:
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": f"layer-{layer}",
            "outputFormat": "json",
            "srsName": "EPSG:2193",
            # Axis order for EPSG:4326 in WFS 2.0 is latitude, longitude.
            "bbox": f"{SOUTH},{WEST},{NORTH},{EAST},urn:ogc:def:crs:EPSG::4326",
        }
        with _client() as client:
            response = client.get(f"{LDS}/wfs", params=params, headers=_lds_headers())
            response.raise_for_status()
            return response.json()

    return _cached_json(raw / "linz" / f"layer-{layer}.json", fetch).get("features", [])


# --- LINZ Data Service: rasters (Exports API) ------------------------------------------------


def multibeam_path(raw: Path) -> Path:
    """The 20 m multibeam model clipped to the box, as a GeoTIFF in its native UTM zone.

    LDS rasters are not served by WFS. The Exports API cuts the box out on the server and
    hands back a zip; that needs a key allowed to create exports (scope "exports:write").
    """
    path = raw / "linz" / f"layer-{MULTIBEAM_LAYER}.tif"
    if path.exists():
        return path
    headers = _lds_headers()
    extent = {
        "type": "Polygon",
        "coordinates": [
            [[WEST, SOUTH], [EAST, SOUTH], [EAST, NORTH], [WEST, NORTH], [WEST, SOUTH]]
        ],
    }
    request = {
        "crs": MULTIBEAM_CRS,
        "items": [{"item": f"{LDS}/api/v1.x/layers/{MULTIBEAM_LAYER}/"}],
        "formats": {"grid": "image/tiff;subtype=geotiff"},
        "extent": extent,
    }
    with _client() as client:
        response = client.post(f"{LDS}/api/v1.x/exports/", json=request, headers=headers)
        if response.status_code in (401, 403):
            detail = response.json().get("errors", {}).get("detail", response.status_code)
            raise MissingKey(
                f"the LINZ Exports API refused LINZ_API_KEY: {detail}. Edit the key at "
                "data.linz.govt.nz (your profile, API keys) and allow it to create exports."
            )
        response.raise_for_status()
        export = response.json()
        for _ in range(120):
            if export["state"] in ("complete", "error", "cancelled", "gone"):
                break
            time.sleep(5)
            export = client.get(export["url"], headers=headers).json()
        if export["state"] != "complete":
            raise RuntimeError(f"LDS export of layer {MULTIBEAM_LAYER} ended as {export['state']}")
        archive = client.get(export["download_url"], headers=headers)
        archive.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
        tiffs = [name for name in bundle.namelist() if name.lower().endswith((".tif", ".tiff"))]
        if len(tiffs) != 1:
            raise RuntimeError(f"expected one GeoTIFF in the export, found {tiffs}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bundle.read(tiffs[0]))
    return path


def warp_to_fine(path: Path, res_m: int) -> np.ndarray:
    """Reproject a raster onto the nested fine grid at res_m, bilinear (NaN = no data).

    Used for the multibeam model, which arrives in UTM zone 60S at 20 m: this is the one
    resampling it gets.
    """
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject

    out = np.full(grid.fine_shape(res_m), np.nan, dtype=np.float32)
    with rasterio.open(path) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=out,
            src_nodata=src.nodata,
            dst_transform=from_origin(grid.WEST_E, grid.NORTH_N, res_m, res_m),
            dst_crs=grid.CRS,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
        )
    return out


# --- DOC habitat map ----------------------------------------------------------------------


def doc_habitat_features(raw: Path) -> list[dict]:
    """Habitat polygons that touch the box, as GeoJSON in NZTM."""

    def fetch() -> dict:
        features, offset = [], 0
        with _client() as client:
            while True:
                params = {
                    "where": "1=1",
                    "geometry": f"{WEST},{SOUTH},{EAST},{NORTH}",
                    "geometryType": "esriGeometryEnvelope",
                    "inSR": "4326",
                    "spatialRel": "esriSpatialRelIntersects",
                    "outFields": "Habitat,Substrate,Zone,Depth",
                    "outSR": "2193",
                    "orderByFields": "OBJECTID",
                    "resultOffset": offset,
                    "f": "geojson",
                }
                response = client.get(DOC_HABITAT, params=params)
                response.raise_for_status()
                page = response.json()
                features += page.get("features", [])
                if not page.get("exceededTransferLimit") and not (page.get("properties") or {}).get(
                    "exceededTransferLimit"
                ):
                    break
                offset = len(features)
        return {"type": "FeatureCollection", "features": features}

    return _cached_json(raw / "doc" / "habitat.json", fetch)["features"]


# --- Global background grid -------------------------------------------------------------------

GEBCO_STEP_CELLS = 5  # GEBCO's own grid is about 450 m, so every fifth cell is enough


def gebco_heights(raw: Path, to_lonlat) -> np.ndarray:
    """GEBCO height above mean sea level at every fifth cell centre (a coarse lattice).

    Returns an array of shape (rows, cols, 3): easting, northing, height in metres.
    The public Open Topo Data service takes 100 points a call, one call a second.
    """
    rows = np.arange(GEBCO_STEP_CELLS // 2, grid.NROWS, GEBCO_STEP_CELLS)
    cols = np.arange(GEBCO_STEP_CELLS // 2, grid.NCOLS, GEBCO_STEP_CELLS)
    rr, cc = np.meshgrid(rows, cols, indexing="ij")
    easting, northing = grid.cell_centre(rr, cc)
    lon, lat = to_lonlat(easting.ravel(), northing.ravel())

    def fetch() -> dict:
        heights = []
        with _client() as client:
            for start in range(0, len(lon), 100):
                where = "|".join(
                    f"{y:.5f},{x:.5f}"
                    for x, y in zip(lon[start : start + 100], lat[start : start + 100], strict=True)
                )
                response = client.get(GEBCO, params={"locations": where})
                response.raise_for_status()
                heights += [result["elevation"] for result in response.json()["results"]]
                time.sleep(1.1)
        return {"heights": heights}

    heights = np.array(_cached_json(raw / "gebco" / "lattice.json", fetch)["heights"], dtype=float)
    return np.stack([easting, northing, heights.reshape(easting.shape)], axis=2)
