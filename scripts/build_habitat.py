#!/usr/bin/env python3
"""Build the snapper habitat index the site shows.

Run by hand from the repo root, after scripts/build_seabed.py or after changing the
species file:

    uv run python scripts/build_habitat.py

It reads the seabed grids (web/public/seabed/), the species file
(src/breamfish/species/snapper.toml), the no-take reserve (web/public/layers/) and the
table of places snapper were recorded (src/breamfish/species/snapper_records.csv), and
writes

    web/public/habitat/manifest.json     everything the site prints about the index
    web/public/habitat/*.bin.gz          the index and each factor, per season, and reach
    web/public/habitat/shore.geojson     the index along the mainland shore
    docs/habitat-report.md               the numbers of this build

Review the diff and commit those. The formula is in src/breamfish/habitat.py and the
method is described in docs/habitat.md. Standard library only, and no network.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import random
import sys
from array import array
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from math import inf
from pathlib import Path

from breamfish import config, grids, habitat, nztm

ROOT = Path(__file__).resolve().parent.parent

# Suitabilities and the index run from 0 to 1 and are stored in 200 steps: stored 1 is
# 0, stored 201 is 1, and stored 0 is "not rated" as in every other layer.
STEPS = 200
SCORE = {"dtype": "uint8", "scale": 1 / STEPS, "offset": -1 / STEPS}

REACH_BIT = {"boat": 1, "kayak": 2, "shore": 4}

SOURCE_LABELS = {
    "tagging": "Caught for tagging (Ministry for Primary Industries tag database)",
    "trawl": "Research trawl tows that caught snapper (NIWA)",
    "sighting": "Photographed by divers and anglers (iNaturalist)",
    "divers": "Diver survey sites (1990 to 1993)",
}

LIMITS = [
    "It ranks places within the bay against each other. It does not say how many "
    "snapper are in the bay: in the November 2020 trawl survey, the stretch of coast "
    "from Bream Bay to Cape Rodney held fewer snapper for its area than any other "
    "part of the survey.",
    "It is for larger snapper, of about 27 cm and over. Small snapper use the harbour "
    "and its seagrass, and are not what this shows.",
    "It knows nothing of the day: tide, wind, water temperature, bait in the water and "
    "the time of day are not in it. The conditions panel covers what the weather is "
    "doing; nothing here covers what the fish are doing.",
    "The squares are 100 m across, and bottom type away from charted rock comes from "
    "a habitat map drawn at a coarse scale in 2010. A reef the chart and that map do "
    "not show is not here either.",
    "The weights and several of the curve points are judgement, marked as such on "
    "this page. None of it has been fitted to catches, because no record of catches "
    "in this bay is public.",
]


def stored(value: float | None) -> int:
    return 0 if value is None else 1 + round(max(0.0, min(1.0, value)) * STEPS)


# Stored in place of a class boundary that no cell reaches; above any stored index.
NEVER = 255


def stored_break(value: float) -> int:
    return NEVER if value == inf else stored(value)


def unstored(code: int) -> float | None:
    return None if code == 0 else (code - 1) / STEPS


# --- Inputs -----------------------------------------------------------------------------


@dataclass
class Inputs:
    grid: grids.Grid
    sea: list[bool]
    depth: list[float | None]  # metres below chart datum
    bottom: list[str | None]  # class key, None where not mapped
    reef: list[float | None]  # metres to the nearest reef cell
    shore: list[float | None]  # metres to the mainland shore
    reserve: list[bool]  # inside a no-take reserve
    bottom_labels: dict[str, str]
    seabed_built: str


def inside(rings: list[list[tuple[float, float]]], x: float, y: float) -> bool:
    """Is a point inside a polygon? rings is the outline followed by any holes."""
    hit = False
    for ring in rings:
        for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1], strict=True):
            if (y0 > y) != (y1 > y) and x < x0 + (x1 - x0) * (y - y0) / (y1 - y0):
                hit = not hit
    return hit


def polygons_nztm(collection: dict) -> list[list[list[tuple[float, float]]]]:
    """Every polygon of a GeoJSON collection in degrees, as rings of NZTM points."""
    out = []
    for feature in collection.get("features", []):
        geometry = feature["geometry"]
        polygons = (
            [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
        )
        for polygon in polygons:
            out.append([[nztm.project(lon, lat) for lon, lat, *_ in ring] for ring in polygon])
    return out


def cells_inside(grid: grids.Grid, polygons) -> list[bool]:
    """Which cells have their centre inside any of the polygons."""
    out = [False] * grid.cells
    for rings in polygons:
        xs = [x for x, _ in rings[0]]
        ys = [y for _, y in rings[0]]
        col0 = max(0, int((min(xs) - grid.west_e) // grid.cell_m))
        col1 = min(grid.ncols - 1, int((max(xs) - grid.west_e) // grid.cell_m))
        row0 = max(0, int((grid.north_n - max(ys)) // grid.cell_m))
        row1 = min(grid.nrows - 1, int((grid.north_n - min(ys)) // grid.cell_m))
        for row in range(row0, row1 + 1):
            for col in range(col0, col1 + 1):
                index = row * grid.ncols + col
                if not out[index] and inside(rings, *grid.centre(index)):
                    out[index] = True
    return out


def load_inputs(seabed: Path, reserves: Path) -> Inputs:
    manifest = grids.load_manifest(seabed)
    grid = grids.grid_of(manifest)
    layers = manifest["layers"]
    source = grids.read_stored(seabed / layers["depth_source"]["file"], "uint8", grid.cells)
    kinds = grids.read_stored(seabed / layers["bottom"]["file"], "uint8", grid.cells)
    key_of = {c["code"]: c["key"] for c in layers["bottom"]["classes"]}
    return Inputs(
        grid=grid,
        sea=[code != 0 for code in source],
        depth=grids.read_scaled(seabed, layers["depth"], grid.cells),
        bottom=[None if key_of[k] == "unknown" else key_of[k] for k in kinds],
        reef=grids.read_scaled(seabed, layers["reef_distance"], grid.cells),
        shore=grids.read_scaled(seabed, layers["shore_distance"], grid.cells),
        reserve=cells_inside(grid, polygons_nztm(json.loads(reserves.read_text()))),
        bottom_labels={c["key"]: c["label"] for c in layers["bottom"]["classes"]},
        seabed_built=manifest["built"],
    )


def load_records(path: Path) -> list[dict]:
    with path.open() as handle:
        return list(csv.DictReader(line for line in handle if not line.startswith("#")))


# --- The index ----------------------------------------------------------------------------


@dataclass
class Built:
    """The grids as stored integers, keyed by file name, and everything said about them."""

    layers: dict[str, array]
    manifest: dict
    shore: dict
    facts: dict


def window_mean(values: list[float | None], grid: grids.Grid, half: int) -> list[float | None]:
    """The mean of the rated cells within `half` cells east-west and north-south of each
    cell. None where there are none."""
    ncols, nrows = grid.ncols, grid.nrows
    width = ncols + 1
    total = [0.0] * (width * (nrows + 1))
    count = [0] * (width * (nrows + 1))
    for row in range(nrows):
        run_total, run_count = 0.0, 0
        above, here = row * width, (row + 1) * width
        for col in range(ncols):
            value = values[row * ncols + col]
            if value is not None:
                run_total += value
                run_count += 1
            total[here + col + 1] = total[above + col + 1] + run_total
            count[here + col + 1] = count[above + col + 1] + run_count
    out: list[float | None] = [None] * grid.cells
    for row in range(nrows):
        top, bottom = max(0, row - half) * width, min(nrows, row + half + 1) * width
        for col in range(ncols):
            left, right = max(0, col - half), min(ncols, col + half + 1)
            n = (
                count[bottom + right]
                - count[top + right]
                - count[bottom + left]
                + count[top + left]
            )
            if n:
                t = (
                    total[bottom + right]
                    - total[top + right]
                    - total[bottom + left]
                    + total[top + left]
                )
                out[row * ncols + col] = t / n
    return out


def rank_in(ranked: list[float], value: float) -> float:
    """The share of a sorted background that lies below a value (a tie counts half)."""
    return (bisect_left(ranked, value) + bisect_right(ranked, value)) / 2 / len(ranked)


def validate(species, index: dict[str, list], inputs: Inputs, records: list[dict]) -> dict:
    """How the index ranks the places snapper were recorded, against the bay as a whole.

    Each record is compared with the index of its own season. Its place is taken as the
    window around its stated position (config.RECORD_WINDOW_M), and so is every place it
    is compared with.
    """
    grid = inputs.grid
    half = round(config.RECORD_WINDOW_M / grid.cell_m)
    smoothed = {season: window_mean(values, grid, half) for season, values in index.items()}
    background = {
        season: sorted(
            v for i, v in enumerate(values) if v is not None and index[season][i] is not None
        )
        for season, values in smoothed.items()
    }
    ranks: dict[tuple[str, str], list[float]] = {}
    unused = {"no_month": 0, "outside_or_no_water": 0}
    for record in records:
        if not record["month"]:
            unused["no_month"] += 1
            continue
        season = species.season_of(int(record["month"]))
        cell = grid.cell_of(*nztm.project(float(record["lon"]), float(record["lat"])))
        value = None if cell is None else smoothed[season][cell]
        if value is None:
            unused["outside_or_no_water"] += 1
            continue
        ranks.setdefault((record["source"], season), []).append(rank_in(background[season], value))

    def group(label_key: str, season: str | None, values: list[float]) -> dict:
        chooser = random.Random(1)
        n = len(values)
        row = {
            "source": label_key,
            "label": SOURCE_LABELS.get(label_key, "All records"),
            "season": season,
            "places": n,
            "auc": round(sum(values) / n, 3),
            "share_in_top_two_fifths": round(sum(v >= 0.6 for v in values) / n, 3),
        }
        if n >= 20:
            means = sorted(sum(chooser.choices(values, k=n)) / n for _ in range(2000))
            row["auc_low"], row["auc_high"] = round(means[50], 3), round(means[1949], 3)
        return row

    groups = []
    everything: list[float] = []
    for source in SOURCE_LABELS:
        of_source: list[float] = []
        for season in species.seasons:
            values = ranks.get((source, season), [])
            if values:
                groups.append(group(source, season, values))
                of_source += values
        if of_source:
            groups.append(group(source, None, of_source))
            everything += of_source
    if everything:
        groups.append(group("all", None, everything))
    return {
        "window_m": config.RECORD_WINDOW_M,
        "records": len(records),
        "unused": unused,
        "groups": groups,
        "how_to_read": "AUC is the chance that the index at a place snapper were recorded "
        "is higher than at a place picked at random from the bay's rated water in the "
        "same season. 0.5 is no better than chance. With no skill, 0.4 of the places "
        "would fall in the top two fifths.",
        "cautions": [
            "These are places someone caught or saw snapper, not a survey of where "
            "snapper are and are not. Tagging boats and trawlers work ground that suits "
            "their gear: trawls cannot fish reef.",
            "Most of the tagging records are one programme in November and December "
            "1993, and their positions are given to the nearest minute of arc, about "
            "1.5 km by 1.9 km. Each place is therefore compared as the average of the "
            "index within 1 km of it, which blurs anything finer.",
            "Places fishing is good are not the same as places snapper are: gear, "
            "bait, tide and time of day decide a catch.",
        ],
    }


def build(species: habitat.Species, inputs: Inputs, records: list[dict]) -> Built:
    grid = inputs.grid
    cells = grid.cells
    seasons = list(species.seasons)
    rated = [inputs.sea[i] and not inputs.reserve[i] for i in range(cells)]
    values_of = {"depth": inputs.depth, "bottom": inputs.bottom, "reef_distance": inputs.reef}
    weights = {factor.key: factor.weight for factor in species.factors}

    # Each factor's suitability, stored and read back so that the index is worked out
    # from exactly the numbers the site shows beside it.
    layers: dict[str, array] = {}
    parts: dict[tuple[str, str], list[float | None]] = {}
    files: dict[str, dict | str] = {}
    for factor in species.factors:
        source = values_of[factor.input]
        for season in seasons if factor.seasonal else [""]:
            codes = array(
                "B",
                (
                    stored(factor.suitability(source[i], season)) if rated[i] else 0
                    for i in range(cells)
                ),
            )
            name = f"{species.key}_{factor.key}{'_' + season if season else ''}.bin.gz"
            layers[name] = codes
            parts[(factor.key, season)] = [unstored(code) for code in codes]
            if season:
                files.setdefault(factor.key, {})[season] = name
            else:
                files[factor.key] = name

    index: dict[str, list[float | None]] = {}
    for season in seasons:
        columns = [(f.key, parts[(f.key, season if f.seasonal else "")]) for f in species.factors]
        codes = array("B", bytes(cells))
        for i in range(cells):
            if rated[i]:
                codes[i] = stored(habitat.combine({key: col[i] for key, col in columns}, weights))
        layers[f"{species.key}_index_{season}.bin.gz"] = codes
        index[season] = [unstored(code) for code in codes]

    # Five classes, each a fifth of the season's rated water. The curves give the shape
    # of each season, not how one season compares with another, so the classes are cut
    # season by season: "highest" is the best fifth of the bay for that time of year.
    breaks = {
        season: habitat.fifths([v for v in index[season] if v is not None]) for season in seasons
    }
    class_cells = {
        season: [
            sum(
                1
                for v in index[season]
                if v is not None and habitat.class_of(v, breaks[season]) == c
            )
            for c in range(1, 6)
        ]
        for season in seasons
    }

    # Reach: which styles of fishing get to each cell.
    reach = array("B", bytes(cells))
    for i in range(cells):
        if not inputs.sea[i]:
            continue
        for style, limit in config.REACH_M.items():
            if limit is None or (inputs.shore[i] is not None and inputs.shore[i] <= limit):
                reach[i] |= REACH_BIT[style]
    layers["reach.bin.gz"] = reach

    # The shore: each cell a cast can reach, rated by the water around it.
    features = []
    for i in range(cells):
        if not (reach[i] & REACH_BIT["shore"]) or not rated[i]:
            continue
        row, col = divmod(i, grid.ncols)
        near = [
            r * grid.ncols + c
            for r in range(max(0, row - 1), min(grid.nrows, row + 2))
            for c in range(max(0, col - 1), min(grid.ncols, col + 2))
        ]
        classes = {}
        for season in seasons:
            around = [index[season][j] for j in near if index[season][j] is not None]
            classes[season] = habitat.class_of(sum(around) / len(around), breaks[season])
        lon, lat = nztm.unproject(*grid.centre(i))
        features.append(
            {
                "type": "Feature",
                "properties": classes,
                "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
            }
        )
    shore = {"type": "FeatureCollection", "features": features}

    validation = validate(species, index, inputs, records)
    spec = species.spec
    factors = []
    for factor in species.factors:
        entry = {
            k: v for k, v in factor.spec.items() if k not in ("input",) and not isinstance(v, bool)
        }
        entry["files"] = files[factor.key]
        if "scores" in entry:
            entry["class_labels"] = {key: inputs.bottom_labels[key] for key in entry["scores"]}
        factors.append(entry)

    reserve_cells = sum(1 for i in range(cells) if inputs.sea[i] and inputs.reserve[i])
    manifest = {
        "schema": 1,
        "built": dt.date.today().isoformat(),
        "seabed_built": inputs.seabed_built,
        "species": {
            key: " ".join(str(spec[key]).split())
            for key in ("key", "name", "scientific_name", "applies_to", "summary")
        },
        "grid": {
            "west_e": grid.west_e,
            "north_n": grid.north_n,
            "cell_m": grid.cell_m,
            "ncols": grid.ncols,
            "nrows": grid.nrows,
        },
        "seasons": species.seasons,
        # value = offset + scale * stored, for the index and for every factor.
        "score": SCORE,
        "index": {
            "files": {season: f"{species.key}_index_{season}.bin.gz" for season in seasons},
            "how": "The weighted geometric mean of the factors that have data for the cell.",
        },
        "classes": {
            "method": spec["classes"]["method"],
            "labels": spec["classes"]["labels"],
            # A cell is in the class above every boundary its stored index reaches. A
            # boundary no cell reaches (the class above it is empty) is NEVER.
            "breaks_stored": {s: [stored_break(b) for b in breaks[s]] for s in seasons},
            "cells": class_cells,
            "note": "The classes are cut season by season, a fifth of that season's rated "
            "water to each as nearly as can be, so the highest class is the best of the "
            "bay for that time of year. Water with the same index always shares a class, "
            "and where the curves are flat much of the bay has the same index, so a class "
            "can hold far more or less than a fifth. One season's map cannot be compared "
            "with another's.",
        },
        "factors": factors,
        "references": spec["reference"],
        "not_rated": {
            "reserve_cells": reserve_cells,
            "note": "Water inside a no-take marine reserve is not rated.",
        },
        "reach": {
            "file": "reach.bin.gz",
            "dtype": "uint8",
            "bits": REACH_BIT,
            "within_m_of_mainland_shore": config.REACH_M,
            "cells": {
                style: sum(1 for i in range(cells) if rated[i] and reach[i] & bit)
                for style, bit in REACH_BIT.items()
            },
            "shore_points": "shore.geojson",
            "note": "Round figures, not rules and not safety limits. Islands do not "
            "count as shore. Whether a stretch of shore can be reached on foot is not "
            "checked.",
        },
        "validation": validation,
        "limits": LIMITS,
    }
    facts = {
        "rated_cells": sum(rated),
        "reserve_cells": reserve_cells,
        "sea_cells": sum(inputs.sea),
        "breaks": breaks,
        "class_cells": class_cells,
        "shore_points": len(features),
        "reach": manifest["reach"]["cells"],
        "validation": validation,
        "bottom_not_mapped": sum(1 for i in range(cells) if rated[i] and inputs.bottom[i] is None),
        "mean_suitability": {
            f"{key}{' (' + season + ')' if season else ''}": round(
                sum(v for v in values if v is not None)
                / max(1, sum(1 for v in values if v is not None)),
                3,
            )
            for (key, season), values in parts.items()
        },
    }
    return Built(layers, manifest, shore, facts)


# --- Writing ------------------------------------------------------------------------------


def report(species: habitat.Species, facts: dict, built: str) -> str:
    seasons = list(species.seasons)
    lines = [
        f"# {species.name} habitat index: what this build holds",
        "",
        f"Written by `scripts/build_habitat.py` on {built}. Do not edit by hand; the "
        "method is in [habitat.md](habitat.md).",
        "",
        f"- Water rated: {facts['rated_cells']:,} cells of 100 m "
        f"(of {facts['sea_cells']:,}; {facts['reserve_cells']:,} are inside the no-take "
        "reserve and are not rated).",
        f"- Bottom type not mapped, so left out of the index there: "
        f"{facts['bottom_not_mapped']:,} cells.",
        f"- Within reach: kayak {facts['reach']['kayak']:,} cells, shore "
        f"{facts['reach']['shore']:,} cells; {facts['shore_points']:,} points along the shore.",
        "",
        "## Share of the rated water in each class, by season",
        "",
        "A boundary is the lowest index in the class above it. Water with the same index "
        "shares a class, so a class is larger or smaller than a fifth where much of the "
        'bay has one index, and "none" marks a class nothing reaches.',
        "",
        "| Season | Boundaries | Lowest | Low | Middle | High | Highest |",
        "|---|---|---|---|---|---|---|",
    ]
    for season in seasons:
        counts = facts["class_cells"][season]
        lines.append(
            f"| {season.capitalize()} | "
            + ", ".join("none" if b == inf else f"{b:.3f}" for b in facts["breaks"][season])
            + " | "
            + " | ".join(f"{100 * c / sum(counts):.0f}%" for c in counts)
            + " |"
        )
    lines += [
        "",
        "## Mean suitability of each factor over the rated water",
        "",
        "| Factor | Mean |",
        "|---|---|",
    ]
    lines += [f"| {name} | {value:.2f} |" for name, value in facts["mean_suitability"].items()]
    v = facts["validation"]
    lines += [
        "",
        "## Against the places snapper were recorded",
        "",
        v["how_to_read"],
        "",
        f"{v['records']} places and times are in the table. {v['unused']['no_month']} give no "
        f"month and {v['unused']['outside_or_no_water']} have no rated water within "
        f"{v['window_m']} m; those are not used.",
        "",
        "| Records | Season | Places | AUC | 95% interval | In the top two fifths |",
        "|---|---|---|---|---|---|",
    ]
    for g in v["groups"]:
        interval = f"{g['auc_low']:.2f} to {g['auc_high']:.2f}" if "auc_low" in g else "too few"
        lines.append(
            f"| {g['label']} | {(g['season'] or 'all').capitalize()} | {g['places']} | "
            f"{g['auc']:.2f} | {interval} | {100 * g['share_in_top_two_fifths']:.0f}% |"
        )
    lines += ["", "Cautions:", ""] + [f"- {text}" for text in v["cautions"]] + [""]
    return "\n".join(lines)


def write(species: habitat.Species, built: Built, out: Path, report_path: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.bin.gz"):
        stale.unlink()
    for name, values in built.layers.items():
        grids.write_stored(out / name, values)
    (out / "shore.geojson").write_text(json.dumps(built.shore, separators=(",", ":")) + "\n")
    (out / "manifest.json").write_text(
        json.dumps(built.manifest, indent=1, ensure_ascii=False) + "\n"
    )
    report_path.write_text(report(species, built.facts, built.manifest["built"]))
    size = sum(path.stat().st_size for path in out.iterdir())
    print(f"wrote {len(built.layers) + 2} files to {out} ({size / 1024:.0f} kB) and {report_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--species", default="snapper")
    parser.add_argument("--seabed", type=Path, default=ROOT / "web" / "public" / "seabed")
    parser.add_argument(
        "--reserves", type=Path, default=ROOT / "web" / "public" / "layers" / "reserves.geojson"
    )
    parser.add_argument("--out", type=Path, default=ROOT / "web" / "public" / "habitat")
    parser.add_argument("--report", type=Path, default=ROOT / "docs" / "habitat-report.md")
    args = parser.parse_args()
    species = habitat.load_species(args.species)
    inputs = load_inputs(args.seabed, args.reserves)
    records = load_records(habitat.SPECIES_DIR / f"{args.species}_records.csv")
    write(species, build(species, inputs, records), args.out, args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
