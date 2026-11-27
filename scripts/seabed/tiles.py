"""Shade grids as map tiles: Web Mercator, 256 pixels square, in one PMTiles archive.

The site's map already reads its basemap from a PMTiles archive: one static file, read
a few kilobytes at a time. The relief goes the same way, so there is still no tile
server and nothing to fetch from anybody else.

The finest zoom is resampled once from the shade grid. Every coarser zoom is the mean of
the four pixels under each of its own, which for slopes this gentle is what shading a
smoother seabed would give. A tile with no shade in it is left out of the archive.
"""

from __future__ import annotations

import io
import warnings
from pathlib import Path

import numpy as np

from seabed import grid, relief

TILE_PX = 256
WEB_MERCATOR = "EPSG:3857"
HALF_WORLD_M = 20037508.342789244
# The finest zoom is resampled this many tiles square at a time.
CHUNK_TILES = 4


def tile_size_m(zoom: int) -> float:
    """The side of a tile in Web Mercator metres (which are not metres on the ground)."""
    return 2 * HALF_WORLD_M / 2**zoom


def tile_range(zoom: int, west: float, south: float, east: float, north: float):
    """The tiles that touch a Web Mercator box: (x0, y0, x1, y1), the last two exclusive."""
    size = tile_size_m(zoom)
    x0 = int(np.floor((west + HALF_WORLD_M) / size))
    x1 = int(np.ceil((east + HALF_WORLD_M) / size))
    y0 = int(np.floor((HALF_WORLD_M - north) / size))
    y1 = int(np.ceil((HALF_WORLD_M - south) / size))
    return x0, y0, x1, y1


def finest(stored: np.ndarray, res_m: int, zoom: int) -> dict:
    """Stored shade on a nested NZTM grid of res_m cells, as tiles at one zoom.

    Returns {(x, y): int8 array of TILE_PX square} for the tiles that have any shade.
    Resampled bilinearly, a few tiles at a time, each from the part of the grid under it.
    """
    from rasterio.transform import from_origin
    from rasterio.warp import Resampling, reproject, transform_bounds

    rows, cols = stored.shape
    box = transform_bounds(
        grid.CRS,
        WEB_MERCATOR,
        grid.WEST_E,
        grid.SOUTH_N,
        grid.EAST_E,
        grid.NORTH_N,
        densify_pts=101,
    )
    x0, y0, x1, y1 = tile_range(zoom, *box)
    size = tile_size_m(zoom)
    margin = 4  # source cells kept around the part of the grid a chunk needs
    tiles = {}
    for cy in range(y0, y1, CHUNK_TILES):
        for cx in range(x0, x1, CHUNK_TILES):
            nx, ny = min(CHUNK_TILES, x1 - cx), min(CHUNK_TILES, y1 - cy)
            west, north = cx * size - HALF_WORLD_M, HALF_WORLD_M - cy * size
            east, south = west + nx * size, north - ny * size
            w, s, e, n = transform_bounds(
                WEB_MERCATOR, grid.CRS, west, south, east, north, densify_pts=21
            )
            c_lo = max(0, int((w - grid.WEST_E) / res_m) - margin)
            c_hi = min(cols, int(np.ceil((e - grid.WEST_E) / res_m)) + margin)
            r_lo = max(0, int((grid.NORTH_N - n) / res_m) - margin)
            r_hi = min(rows, int(np.ceil((grid.NORTH_N - s) / res_m)) + margin)
            if c_lo >= c_hi or r_lo >= r_hi:
                continue
            source = stored[r_lo:r_hi, c_lo:c_hi]
            if not (source != relief.NO_SHADE).any():
                continue
            out = np.full((ny * TILE_PX, nx * TILE_PX), relief.NO_SHADE, dtype=np.int8)
            reproject(
                source=np.ascontiguousarray(source),
                destination=out,
                src_transform=from_origin(
                    grid.WEST_E + c_lo * res_m, grid.NORTH_N - r_lo * res_m, res_m, res_m
                ),
                src_crs=grid.CRS,
                src_nodata=relief.NO_SHADE,
                dst_transform=from_origin(west, north, size / TILE_PX, size / TILE_PX),
                dst_crs=WEB_MERCATOR,
                dst_nodata=relief.NO_SHADE,
                resampling=Resampling.bilinear,
            )
            for ty in range(ny):
                for tx in range(nx):
                    tile = out[ty * TILE_PX : (ty + 1) * TILE_PX, tx * TILE_PX : (tx + 1) * TILE_PX]
                    if (tile != relief.NO_SHADE).any():
                        tiles[(cx + tx, cy + ty)] = tile.copy()
    return tiles


def coarser(tiles: dict) -> dict:
    """The next zoom out: each pixel the mean of the four under it.

    A pixel has shade when at least two of its four have, so the edge of the survey
    neither grows nor shrinks from one zoom to the next.
    """
    parents = {}
    for x, y in sorted({(x // 2, y // 2) for x, y in tiles}):
        four = np.full((2 * TILE_PX, 2 * TILE_PX), relief.NO_SHADE, dtype=np.int8)
        for dy in (0, 1):
            for dx in (0, 1):
                child = tiles.get((2 * x + dx, 2 * y + dy))
                if child is not None:
                    four[dy * TILE_PX : (dy + 1) * TILE_PX, dx * TILE_PX : (dx + 1) * TILE_PX] = (
                        child
                    )
        blocks = four.reshape(TILE_PX, 2, TILE_PX, 2).transpose(0, 2, 1, 3).reshape(TILE_PX, -1, 4)
        valid = blocks != relief.NO_SHADE
        count = valid.sum(axis=2)
        total = np.where(valid, blocks, 0).sum(axis=2, dtype=np.int32)
        mean = np.rint(total / np.maximum(count, 1))
        parent = np.where(count >= 2, mean, relief.NO_SHADE).astype(np.int8)
        if (parent != relief.NO_SHADE).any():
            parents[(x, y)] = parent
    return parents


def pyramid(stored: np.ndarray, res_m: int, min_zoom: int, max_zoom: int) -> dict:
    """{zoom: {(x, y): int8 tile}} from max_zoom out to min_zoom."""
    levels = {max_zoom: finest(stored, res_m, max_zoom)}
    for zoom in range(max_zoom - 1, min_zoom - 1, -1):
        levels[zoom] = coarser(levels[zoom + 1])
    return levels


def png(tile: np.ndarray) -> bytes | None:
    """One tile as a PNG with a palette, or None if nothing in it would show."""
    import rasterio
    from rasterio.io import MemoryFile

    image = relief.pixels(tile)
    if not image.any():
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", rasterio.errors.NotGeoreferencedWarning)
        with MemoryFile() as memory:
            with memory.open(
                driver="PNG", width=TILE_PX, height=TILE_PX, count=1, dtype="uint8", zlevel=9
            ) as out:
                out.write(image, 1)
                out.write_colormap(1, relief.PALETTE)
            return memory.read()


def write_archive(path: Path, levels: dict, bounds, attribution: str) -> dict:
    """Write the tiles of every zoom as one PMTiles archive; returns what was written.

    bounds is (west, south, east, north) in degrees. Tiles go in the archive's own
    order, and nothing in the file depends on the clock, so the same tiles give the
    same bytes.
    """
    from pmtiles.tile import Compression, TileType, zxy_to_tileid
    from pmtiles.writer import Writer

    encoded = []
    for zoom, tiles in levels.items():
        for (x, y), tile in tiles.items():
            data = png(tile)
            if data is not None:
                encoded.append((zxy_to_tileid(zoom, x, y), data))
    encoded.sort()
    if not encoded:
        raise ValueError(f"no tile has any shade in it: nothing to write to {path.name}")
    west, south, east, north = bounds
    buffer = io.BytesIO()
    writer = Writer(buffer)
    for tile_id, data in encoded:
        writer.write_tile(tile_id, data)
    writer.finalize(
        {
            "tile_type": TileType.PNG,
            "tile_compression": Compression.NONE,
            "min_zoom": min(levels),
            "max_zoom": max(levels),
            "min_lon_e7": round(west * 1e7),
            "min_lat_e7": round(south * 1e7),
            "max_lon_e7": round(east * 1e7),
            "max_lat_e7": round(north * 1e7),
            "center_zoom": min(levels),
        },
        {"attribution": attribution, "type": "overlay", "format": "png"},
    )
    data = buffer.getvalue()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {
        "tiles": len(encoded),
        "bytes": len(data),
        "min_zoom": min(levels),
        "max_zoom": max(levels),
    }
