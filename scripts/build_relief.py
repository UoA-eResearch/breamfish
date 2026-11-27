#!/usr/bin/env python3
"""Build the shaded relief the map lays over the seabed, and the fine roughness layer,
from the 2 m LiDAR and the 20 m multibeam model.

Run by hand from the repo root, after scripts/build_seabed.py:

    uv run python scripts/build_relief.py

It needs no key. The 2 m LiDAR sheets (about 130 MB) come from the public bucket the
first time and are kept in data/seabed/raw/ beside the rest; the multibeam model is the
file build_seabed.py already cached there. It reads the committed seabed grids, and writes

    web/public/tiles/relief_lidar.pmtiles      shaded relief from the LiDAR
    web/public/tiles/relief_multibeam.pmtiles  shaded relief from the multibeam
    web/public/seabed/fine_roughness.bin.gz    rough ground on the 100 m grid
    web/public/seabed/manifest.json            its `relief` and `layers.fine_roughness`
    docs/seabed-report.md                      its last section, on rough ground

Review the diff and commit those together. The method is described in docs/seabed.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_seabed  # noqa: E402
from seabed import depth, grid, publish, relief, report, sources, tiles  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

LIDAR_RES_M = sources.LIDAR_RELIEF_RES_M
MULTIBEAM_RES_M = sources.MULTIBEAM_RES_M
# The LiDAR is read and shaded this many cells square at a time, a whole number of
# 100 m cells, with a halo around each block so that its shade does not show the seam.
BLOCK_CELLS = 2000

# At zoom 16 a pixel of a 256 pixel tile is 1.9 m on the ground at this latitude: the
# LiDAR as it comes. The map's closest view (its zoom 15.5) is drawn from that, and its
# widest (zoom 8) from zoom 9. The multibeam model's cells are 20 m; two zooms out from
# the LiDAR's finest a pixel is 7.7 m, and the map stretches that smoothly from there in.
MIN_ZOOM = 9
LIDAR_MAX_ZOOM = 16
MULTIBEAM_MAX_ZOOM = 14

LIDAR_ARCHIVE = "relief_lidar.pmtiles"
MULTIBEAM_ARCHIVE = "relief_multibeam.pmtiles"
ROUGHNESS_FILE = "fine_roughness.bin.gz"

NOTE = "Shading appears only where the depth was measured, by LiDAR or by multibeam sonar."


# --- Inputs -----------------------------------------------------------------------------


@dataclass
class Inputs:
    # (row, col, rows, cols) in 2 m cells of the nested grid -> NZVD2016 heights there,
    # NaN = no data. The window may reach past the edge of the grid.
    lidar: Callable[[tuple[int, int, int, int]], np.ndarray]
    multibeam_fine: np.ndarray  # model heights on the nested 20 m grid, NaN = no data
    # The 100 m grids as committed by build_seabed.py.
    cell_source: np.ndarray  # depth_source codes
    depth: np.ndarray  # metres below chart datum, NaN on land
    bottom: np.ndarray  # bottom class codes
    bottom_source: np.ndarray  # which source gave each cell its bottom class
    roughness: np.ndarray  # metres about the cell's plane, NaN where there is none
    slope: np.ndarray  # degrees, NaN where there is none


def load_inputs(raw: Path, seabed: Path) -> Inputs:
    print("2 m LiDAR tiles ...")
    paths = sources.lidar_paths(raw, LIDAR_RES_M)
    print("multibeam model ...")
    multibeam = sources.warp_to_fine(sources.multibeam_path(raw), MULTIBEAM_RES_M)
    manifest = json.loads((seabed / "manifest.json").read_text())
    layers = manifest["layers"]

    def stored(name: str) -> np.ndarray:
        layer = layers[name]
        return publish.from_bytes((seabed / layer["file"]).read_bytes(), layer["dtype"])

    def scaled(name: str) -> np.ndarray:
        layer = layers[name]
        scaling = publish.Scaling(layer["dtype"], layer["scale"], layer["offset"])
        return publish.decode(stored(name), scaling)

    return Inputs(
        lidar=lambda window: sources.mosaic(paths, LIDAR_RES_M, window),
        multibeam_fine=multibeam,
        cell_source=stored("depth_source"),
        depth=scaled("depth"),
        bottom=stored("bottom"),
        bottom_source=stored("bottom_source"),
        roughness=scaled("roughness"),
        slope=scaled("slope"),
    )


# --- The build ----------------------------------------------------------------------------


@dataclass
class Built:
    lidar_tiles: dict  # {zoom: {(x, y): stored shade}}
    multibeam_tiles: dict
    fine_roughness: np.ndarray  # metres on the 100 m grid, NaN where there is none
    facts: dict


def shade_lidar(read, max_depth_m: float):
    """The LiDAR, a block at a time: its shade, the roughness of every 10 m square, and
    how much of every 20 m square it covers.

    Returns (stored shade at 2 m, window roughness at 10 m, cover at 20 m).
    """
    res = LIDAR_RES_M
    rows, cols = grid.fine_shape(res)
    halo = relief.halo_cells(res)
    per_window = relief.WINDOW_M // res
    per_cover = MULTIBEAM_RES_M // res
    stored = np.full((rows, cols), relief.NO_SHADE, dtype=np.int8)
    windows = np.full((rows // per_window, cols // per_window), np.nan, dtype=np.float32)
    covered = np.zeros((rows // per_cover, cols // per_cover), dtype=np.float32)
    for row in range(0, rows, BLOCK_CELLS):
        for col in range(0, cols, BLOCK_CELLS):
            high, wide = min(BLOCK_CELLS, rows - row), min(BLOCK_CELLS, cols - col)
            height = read((row - halo, col - halo, high + 2 * halo, wide + 2 * halo))
            if np.isnan(height).all():
                continue
            fine = relief.lidar_sea(height, max_depth_m)
            core = fine[halo:-halo, halo:-halo]
            if np.isnan(core).all():
                continue
            shaded = relief.to_stored(relief.shade(fine, res))
            stored[row : row + high, col : col + wide] = shaded[halo:-halo, halo:-halo]
            windows[
                row // per_window : (row + high) // per_window,
                col // per_window : (col + wide) // per_window,
            ] = relief.window_roughness(core, res)
            covered[
                row // per_cover : (row + high) // per_cover,
                col // per_cover : (col + wide) // per_cover,
            ] = relief.cover(~np.isnan(core), per_cover)
    return stored, windows, covered


def shade_multibeam(multibeam_fine: np.ndarray) -> np.ndarray:
    """Signed shade of the multibeam model's sea, on its own 20 m grid."""
    fine = depth.depth_from_multibeam(multibeam_fine)
    return relief.shade(np.where(depth.is_sea(fine), fine, np.nan), MULTIBEAM_RES_M)


def build(inputs: Inputs, max_depth_m: float = build_seabed.LIDAR_MAX_DEPTH_M) -> Built:
    """Everything between the sources and what is written. No network, no files."""
    lidar, windows, lidar_cover = shade_lidar(inputs.lidar, max_depth_m)
    multibeam_all = shade_multibeam(inputs.multibeam_fine)
    # Where the LiDAR covers at least half of a 20 m square its own shade is drawn, and
    # the multibeam's is left out.
    multibeam = relief.to_stored(np.where(lidar_cover >= 0.5, np.nan, multibeam_all))

    # Rough ground is published for the cells whose depth is the LiDAR's, so a tap that
    # says "depth from LiDAR" is a tap that has it.
    mine = inputs.cell_source == depth.LIDAR.code
    fine_roughness = np.where(mine, relief.cell_roughness(windows), np.nan)
    # As it is stored, to the centimetre, so that the report describes the file.
    fine_roughness = publish.decode(
        publish.encode(fine_roughness, publish.FINE_ROUGHNESS), publish.FINE_ROUGHNESS
    )

    facts = {
        "shaded_km2": {
            "lidar": round(float((lidar != relief.NO_SHADE).sum()) * LIDAR_RES_M**2 / 1e6, 1),
            "multibeam": round(
                float((multibeam != relief.NO_SHADE).sum()) * MULTIBEAM_RES_M**2 / 1e6, 1
            ),
        },
        "surveys_agree": report.shade_agreement(lidar, multibeam_all),
        "rough_ground": report.rough_ground(
            windows,
            fine_roughness,
            inputs.depth,
            inputs.roughness,
            inputs.slope,
            inputs.bottom,
            inputs.bottom_source,
        ),
    }
    return Built(
        tiles.pyramid(lidar, LIDAR_RES_M, MIN_ZOOM, LIDAR_MAX_ZOOM),
        tiles.pyramid(multibeam, MULTIBEAM_RES_M, MIN_ZOOM, MULTIBEAM_MAX_ZOOM),
        fine_roughness,
        facts,
    )


# --- Writing ------------------------------------------------------------------------------


def roughness_layer(facts: dict) -> dict:
    return publish.scaled_layer(
        publish.FINE_ROUGHNESS,
        file=ROUGHNESS_FILE,
        unit="m",
        label="Rough ground",
        note=f"How uneven the bottom is over {relief.WINDOW_M} m: the spread of depth about a "
        f"plane through each {relief.WINDOW_M} m square of the {LIDAR_RES_M} m LiDAR, and of a "
        "cell's hundred squares the third roughest. Only where the depth is from the "
        "LiDAR. Not used by the bottom type or the habitat index.",
        # The steps the map colours it in: the lines the report tries.
        bands_m=list(report.ROUGH_THRESHOLDS_M),
        reading=report.rough_ground_reading(facts["rough_ground"]),
    )


def relief_manifest(archives: list[dict]) -> dict:
    return {
        "built": dt.date.today().isoformat(),
        "note": NOTE,
        "tile_px": tiles.TILE_PX,
        "exaggeration": relief.EXAGGERATION,
        "lights": [
            {"azimuth_deg": azimuth, "altitude_deg": relief.ALTITUDE_DEG, "weight": weight}
            for azimuth, weight in relief.LIGHTS
        ],
        # In the order they are drawn: the LiDAR over the multibeam.
        "archives": archives,
    }


def write(built: Built, tiles_dir: Path, seabed: Path, report_path: Path) -> list[dict]:
    """Write the archives, the layer, and this build's part of the manifest and the report."""
    bounds = build_seabed.lonlat_bounds()
    licence = build_seabed.LICENCE_LINZ
    archives = []
    for key, name, levels, cell_m in (
        ("multibeam", MULTIBEAM_ARCHIVE, built.multibeam_tiles, MULTIBEAM_RES_M),
        ("lidar", LIDAR_ARCHIVE, built.lidar_tiles, LIDAR_RES_M),
    ):
        note = build_seabed.SOURCE_NOTES[key]
        source_name = note["name"].replace(", 10 m", f", {cell_m} m")
        written = tiles.write_archive(tiles_dir / name, levels, bounds, f"{source_name}. {licence}")
        digest = hashlib.sha256((tiles_dir / name).read_bytes()).hexdigest()
        archives.append(
            {
                "key": key,
                "url": f"/tiles/{name}",
                # Part of the address the map asks for, so that a rebuilt archive is
                # never read through a cached piece of the one before it.
                "version": digest[:12],
                **written,
                "cell_m": cell_m,
                "smooth_m": relief.SMOOTH_M[cell_m],
                "name": source_name,
                "url_source": note["url"],
                "licence": note["licence"],
            }
        )
    (seabed / ROUGHNESS_FILE).write_bytes(
        publish.to_bytes(publish.encode(built.fine_roughness, publish.FINE_ROUGHNESS))
    )

    manifest_path = seabed / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["layers"]["fine_roughness"] = roughness_layer(built.facts)
    manifest["relief"] = relief_manifest(archives)
    publish.write_json(manifest_path, manifest)

    before = report_path.read_text() if report_path.exists() else ""
    report_path.write_text(
        report.joined(
            report.without_rough_ground(before), report.rough_ground_markdown(built.facts)
        )
    )
    return archives


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--raw", type=Path, default=ROOT / "data" / "seabed" / "raw")
    parser.add_argument("--seabed", type=Path, default=ROOT / "web" / "public" / "seabed")
    parser.add_argument("--tiles", type=Path, default=ROOT / "web" / "public" / "tiles")
    parser.add_argument("--report", type=Path, default=ROOT / "docs" / "seabed-report.md")
    args = parser.parse_args()
    try:
        inputs = load_inputs(args.raw, args.seabed)
    except sources.MissingKey as error:
        print(
            f"Stopped: the multibeam model is not in {args.raw} and fetching it needs a "
            f"key. {error}",
            file=sys.stderr,
        )
        return 2
    built = build(inputs)
    archives = write(built, args.tiles, args.seabed, args.report)
    for archive in archives:
        print(
            f"{archive['url']}: {archive['bytes'] / 1e6:.1f} MB, {archive['tiles']:,} tiles, "
            f"zoom {archive['min_zoom']} to {archive['max_zoom']}"
        )
    total = sum(archive["bytes"] for archive in archives)
    print(f"both archives: {total / 1e6:.1f} MB; also wrote {ROUGHNESS_FILE} and {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
